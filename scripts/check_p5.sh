#!/usr/bin/env bash
# check_p5.sh — Observation 层通路自检:告警/日报能不能真送到人眼前(飞书)。
#
# 2026-07-14 删掉了原来的「② 手动配置清单覆盖」检查 —— 它 grep 一份文档里有没有
# 「待审推卡片」和「表单」两个词。**它检查的是文档里写没写,不是功能通没通。**
# 这是「假承诺」的标本:一道看着在保护你、实际什么都没验的门。而且它引用的那份文档
# 已经被删了(它携带旧模型),这道门当场变成 grep 一个不存在的文件。
# 规矩:**要么真做出来,要么删掉。**
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① 告警通路(实发;ALERT_DRY_RUN=1 验 dry 投递;HERMES_SKIP=1 跳过)"
if [ "${HERMES_SKIP:-0}" = "1" ]; then pass "跳过(HERMES_SKIP=1)"
elif [ "${ALERT_DRY_RUN:-0}" = "1" ]; then
  OUT=$(python3 -c "from orchestrator import alerts; alerts.send('check_p5 通路自检')" 2>&1)
  if echo "$OUT" | grep -q "alert:dry" && echo "$OUT" | grep -q "check_p5 通路自检"; then
    pass "dry-run 投递链路可见"
  else
    fail "dry-run 投递链路异常"
  fi
elif python3 -c "
from orchestrator import alerts
raise SystemExit(0 if alerts.send('check_p5 通路自检') else 1)"; then pass "告警→飞书 实发成功"
else fail "告警实发失败"; fi

echo; [ "$FAIL" -eq 0 ] && echo "✅ Observation 通路通(告警送得到人眼前)" || echo "❌ 有失败项"
exit "$FAIL"
