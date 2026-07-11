#!/usr/bin/env bash
# 运营 cron 安装(幂等,标记块管理)。默认只打印;--install 真装;--remove 卸载。
# ⚠️ 装机时点=上线(运营库 ZhzJbf 挂 cron);开发期不要装。
# 大刀阔斧后重引擎已删:内容生成走薄执行器 draft_one(现手动,轻调度器见 #8);
# 本 cron 只留数据安全(每日备份)+ 周复盘飞轮,不再挂 orchestrator.run daily/heartbeat。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
ACTION="print"
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
# 每日 23:30 备份运营库(误删可恢复;数据安全底线)
30 23 * * * cd $ROOT && $PY scripts/backup_tables.py >> logs/cron.log 2>&1
# 周日19:00 效果回流采集:非登录 extract skill 抓已发note互动数据写回点赞/收藏 + 按方法论复盘(需 TIKHUB_API_KEY 取列表)
0 19 * * 0 cd $ROOT && $PY -m scripts.collect_metrics --real >> logs/weekly.log 2>&1
# 周复盘飞轮(D2):周日20点,agent读上面采集回的效果数→提SKILL.md改进(人审PR,不自动merge)
0 20 * * 0 cd $ROOT && claude -p \"读运行日志表本周记录与已回流笔记的热度分,总结哪类内容/衣服/关键词表现好,对 qiaohe-skill 的 write-xiaohongshu 或 guanyun-OOTD-text 提出 SKILL.md 改进建议并开 PR,不要自动 merge\" --max-turns 20 --max-budget-usd 1.0 >> logs/weekly.log 2>&1
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
