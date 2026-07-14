#!/usr/bin/env bash
# 运营 cron 安装(幂等,标记块管理)。默认只打印;--install 真装;--remove 卸载。
# ⚠️ 装机时点=上线(运营库 ZhzJbf 挂 cron);开发期不要装。
# 大刀阔斧后重引擎已删:内容生成走薄执行器 draft_one(现手动,轻调度器见 #8);
# 本 cron 只留数据安全(每日备份)+ 周复盘飞轮,不再挂 orchestrator.run daily/heartbeat。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
ACTION="print"

# cron 环境 PATH 精简,脚本按名调用 lark-cli/hermes/claude/BaiduPCS-Go 会 FileNotFoundError(logs/cron.log 实测)。
# 装机时(非交互 bash,无 alias 干扰)解析各工具真实目录 → 拼进 cron 块 PATH。只取绝对路径(排除 alias/function)。
_cron_dirs=""
for _t in python3 lark-cli hermes claude BaiduPCS-Go; do
  _p="$(command -v "$_t" 2>/dev/null || true)"
  case "$_p" in
    /*) _d="$(dirname "$_p")" ;;
    *)  _d="" ;;
  esac
  if [ -n "$_d" ] && [ -d "$_d" ]; then
    case ":$_cron_dirs:" in *":$_d:"*) ;; *) _cron_dirs="${_cron_dirs:+$_cron_dirs:}$_d" ;; esac
  fi
done
CRON_PATH="${_cron_dirs:+$_cron_dirs:}/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
MARK_BEGIN="# BEGIN guanyun-orchestrator"
MARK_END="# END guanyun-orchestrator"

usage() {
  cat <<EOF
用法: $0 [--install|--remove]

默认只打印将安装的 crontab 块。
例:
  $0
  $0 --install
  $0 --remove
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install) ACTION="install" ;;
    --remove) ACTION="remove" ;;
    --help|-h) usage; exit 0 ;;
    *) echo "❌ 未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

BLOCK="$MARK_BEGIN
# cron PATH:装机时解析的工具目录(否则 lark-cli/hermes/claude/BaiduPCS-Go 按名找不到,子进程 FileNotFoundError)
PATH=$CRON_PATH
# 每日 07:50 活 schema 漂移前置探针(ADR-0009 P1):飞书改了字段名/删选项→代码会静默读空/写失败,提前告警别空跑。
50 7 * * * cd $ROOT && $PY scripts/check_schema_drift.py --alert >> logs/cron.log 2>&1
# 每日 08:00 轻调度器派活(#8):每号每模式落一条『待出文案』待人/系统出稿,已在途去重。绝不自动发布、绝不代勾AI声明。
0 8 * * * cd $ROOT && $PY -m scripts.daily_dispatch --write >> logs/cron.log 2>&1
# 网盘投递箱自动打标入库(人往 /巧荷素材/待入库 丢素材 → 自动拉+转码/抽帧+claude看图打标+register,永久分享链接+系统编码)。
# ⚠️ 默认关闭(本机不挂):上线服务器时,取消下一行注释即启用(每日 07:30)。省钱批量、去重不重标、绝不自动发布。
#30 7 * * * cd $ROOT && $PY -m scripts.tag_materials --from-netpan /巧荷素材/待入库 --write >> logs/cron.log 2>&1
# 每周一08:30 真跑综合验收(反'设计到位真跑没到位':verify_usable 逐条过全流程全模式全红线,非0退出=未完全可用记日志)
30 8 * * 1 cd $ROOT && $PY scripts/verify_usable.py --alert >> logs/verify.log 2>&1
# 每日 23:30 备份运营库(误删可恢复;数据安全底线)
30 23 * * * cd $ROOT && $PY scripts/backup_tables.py >> logs/cron.log 2>&1
# 周日19:00 效果回流采集:非登录 extract skill 抓已发note互动数据写回点赞/收藏 + 按方法论复盘(零key SSR,已实测真采赞805;列表从自己base已发笔记读,不需TIKHUB)
0 19 * * 0 cd $ROOT && $PY -m scripts.collect_metrics >> logs/weekly.log 2>&1
# 周复盘飞轮(D2):周日20点,agent读上面采集回的效果数→提SKILL.md改进(人审PR,不自动merge)
0 20 * * 0 cd $ROOT && claude -p \"读运行日志表本周记录与已回流笔记的热度分,总结哪类内容/衣服/关键词表现好,对相关写作技能(技能唯一真源=qiaohe-skill 仓:writing-* / write-xiaohongshu)提出 SKILL.md 改进建议并开 PR,不要自动 merge\" --max-turns 20 --max-budget-usd 1.0 >> logs/weekly.log 2>&1
$MARK_END"

case "$ACTION" in
  install)
    mkdir -p "$ROOT/logs"
    ( crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d"; echo "$BLOCK" ) | crontab -
    echo "✅ 已安装(crontab -l 查看;卸载: $0 --remove)" ;;
  remove)
    crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d" | crontab -
    echo "✅ 已卸载" ;;
  print)
    echo "$BLOCK"
    echo
    echo "(仅预览。真装: $0 --install)"
    echo "注:内容生成暂走薄执行器手动 —— python3 -m scripts.draft_one --account <号> --llm real --write(轻调度器见 #8)" ;;
esac
