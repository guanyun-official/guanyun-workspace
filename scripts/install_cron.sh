#!/usr/bin/env bash
# 推进器 cron 安装(幂等,标记块管理)。默认只打印;--install 真装;--remove 卸载。
# ⚠️ 装机时点=P7 运营库试运行;开发期不要装(避免无人值守跑运营库花钱)。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
CRON_LLM="${GY_CRON_LLM:-real}"
ACTION="print"
MARK_BEGIN="# BEGIN guanyun-orchestrator"
MARK_END="# END guanyun-orchestrator"

usage() {
  cat <<EOF
用法: $0 [--llm stub|real] [--install|--remove]

默认只打印将安装的 crontab 块。--llm 也可用 GY_CRON_LLM=stub|real 指定。
例:
  $0 --llm stub
  $0 --llm stub --install
  $0 --remove
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install) ACTION="install" ;;
    --remove) ACTION="remove" ;;
    --llm)
      shift
      [ "${1:-}" ] || { echo "❌ --llm 需要 stub 或 real" >&2; exit 2; }
      CRON_LLM="$1" ;;
    --help|-h)
      usage
      exit 0 ;;
    *)
      echo "❌ 未知参数: $1" >&2
      usage >&2
      exit 2 ;;
  esac
  shift
done

case "$CRON_LLM" in
  stub|real) ;;
  *) echo "❌ --llm/GY_CRON_LLM 只能是 stub 或 real,当前=$CRON_LLM" >&2; exit 2 ;;
esac

BLOCK="$MARK_BEGIN
# 每日 09:00 排产轮(日报);工作时段每 30 分钟巡检;23:30 备份
0 9 * * * cd $ROOT && $PY -m orchestrator.run --mode daily --llm $CRON_LLM >> logs/cron.log 2>&1
*/30 9-21 * * * cd $ROOT && $PY -m orchestrator.run --mode heartbeat --llm $CRON_LLM >> logs/cron.log 2>&1
30 23 * * * cd $ROOT && $PY scripts/backup_tables.py >> logs/cron.log 2>&1
# 周复盘飞轮(D2):周日20点,agent读运行日志+效果→提SKILL.md改进(人审PR,不自动merge)
0 20 * * 0 cd $ROOT && claude -p \"读运行日志表本周记录与已回流笔记的热度分,总结哪类内容/衣服/关键词表现好,对 qiaohe-skill 的 write-xiaohongshu 或 guanyun-OOTD-text 提出 SKILL.md 改进建议并开 PR,不要自动 merge\" --max-turns 20 --max-budget-usd 1.0 >> logs/weekly.log 2>&1
$MARK_END"

case "$ACTION" in
  install)
    mkdir -p "$ROOT/logs"
    ( crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d"; echo "$BLOCK" ) | crontab -
    echo "✅ 已安装(llm=$CRON_LLM; crontab -l 查看;卸载: $0 --remove)" ;;
  remove)
    crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d" | crontab -
    echo "✅ 已卸载" ;;
  print)
    echo "$BLOCK"
    echo
    echo "(仅预览。真装: $0 --llm $CRON_LLM --install)" ;;
esac
