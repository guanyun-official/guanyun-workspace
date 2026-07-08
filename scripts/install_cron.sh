#!/usr/bin/env bash
# 推进器 cron 安装(幂等,标记块管理)。默认只打印;--install 真装;--remove 卸载。
# ⚠️ 装机时点=P7 切生产/试运行;开发期不要装(避免无人值守跑测试 Base 花钱)。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
MARK_BEGIN="# BEGIN guanyun-orchestrator"
MARK_END="# END guanyun-orchestrator"

BLOCK="$MARK_BEGIN
# 每日 09:00 排产轮(日报);工作时段每 30 分钟巡检;23:30 备份
0 9 * * * cd $ROOT && $PY -m orchestrator.run --mode daily --llm real >> logs/cron.log 2>&1
*/30 9-21 * * * cd $ROOT && $PY -m orchestrator.run --mode heartbeat --llm real >> logs/cron.log 2>&1
30 23 * * * cd $ROOT && $PY scripts/backup_tables.py >> logs/cron.log 2>&1
# 周复盘飞轮(D2):周日20点,agent读运行日志+效果→提SKILL.md改进(人审PR,不自动merge)
0 20 * * 0 cd $ROOT && claude -p \"读运行日志表本周记录与已回流笔记的热度分,总结哪类内容/衣服/关键词表现好,对 qiaohe-skill 的 write-xiaohongshu 或 guanyun-OOTD-text 提出 SKILL.md 改进建议并开 PR,不要自动 merge\" --max-turns 20 --max-budget-usd 1.0 >> logs/weekly.log 2>&1
$MARK_END"

case "${1:-print}" in
  --install)
    mkdir -p "$ROOT/logs"
    ( crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d"; echo "$BLOCK" ) | crontab -
    echo "✅ 已安装(crontab -l 查看;卸载: $0 --remove)" ;;
  --remove)
    crontab -l 2>/dev/null | sed "/$MARK_BEGIN/,/$MARK_END/d" | crontab -
    echo "✅ 已卸载" ;;
  *)
    echo "$BLOCK"
    echo
    echo "(仅预览。真装: $0 --install)" ;;
esac
