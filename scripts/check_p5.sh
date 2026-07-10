#!/usr/bin/env bash
# check_p5.sh — 飞书的脸(lean)。大刀阔斧后去掉 engine heartbeat 端到端验收(引擎已删);
# 留 hermes 告警/日报通路自检 + 手动配置清单覆盖。人依赖项(UI自动化+手机点卡片)见 docs/P2_手动配置清单.md。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① hermes 通路(实发;ALERT_DRY_RUN=1 验 dry 投递;HERMES_SKIP=1 跳过)"
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
raise SystemExit(0 if alerts.send('check_p5 通路自检') else 1)"; then pass "hermes→飞书 实发成功"
else fail "hermes 实发失败"; fi

echo "② 手动配置清单覆盖 自动化+表单 两项"
grep -q "待审推卡片" docs/P2_手动配置清单.md && grep -q "表单" docs/P2_手动配置清单.md \
  && pass "清单完整" || fail "清单缺项"

echo; [ "$FAIL" -eq 0 ] && echo "✅ 飞书的脸验收通过(lean;人测项:UI配自动化→手机点卡片闭环)" || echo "❌ 有失败项"
exit "$FAIL"
