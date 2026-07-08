#!/usr/bin/env bash
# check_p5.sh — P5 飞书的脸验收。人依赖项(UI自动化+手机点卡片)不在本脚本,见 docs/P2_手动配置清单.md。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① 深链/发布包文案单测"
python3 -m unittest tests.test_p5_links 2>&1 | grep -q "^OK" && pass "unittest OK" || fail "单测失败"

echo "② hermes 通路(实发;HERMES_SKIP=1 跳过)"
if [ "${HERMES_SKIP:-0}" = "1" ]; then pass "跳过(HERMES_SKIP=1)"
elif python3 -c "
from orchestrator import alerts
raise SystemExit(0 if alerts.send('check_p5 通路自检') else 1)"; then pass "hermes→飞书 实发成功"
else fail "hermes 实发失败"; fi

echo "③ 巡检/日报消息含记录深链(引擎 dry 轮实测)"
OUT=$(ALERT_DRY_RUN=1 python3 -m orchestrator.run --mode heartbeat 2>&1)
if echo "$OUT" | grep -q "record=rec"; then pass "摘要含记录深链"
else fail "摘要无深链(若当前无催办项则人工复核)"; fi

echo "④ 手动配置清单覆盖 自动化+表单 两项"
grep -q "待审推卡片" docs/P2_手动配置清单.md && grep -q "表单" docs/P2_手动配置清单.md \
  && pass "清单完整" || fail "清单缺项"

echo; [ "$FAIL" -eq 0 ] && echo "✅ P5 代码侧验收通过(人测项:UI配自动化→手机点卡片闭环)" || echo "❌ P5 有失败项"
exit "$FAIL"
