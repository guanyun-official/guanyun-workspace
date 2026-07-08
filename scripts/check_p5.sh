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

echo "③ 引擎 dry 轮跑通(端到端连通;深链正确性见 ① 确定性单测)"
# 原判定 grep record=rec 受 reminders 每日节流+库态双重摆布(当天二次跑即误红),
# 已把「巡检消息含深链」固化为 ① 的确定性单测;此处只验引擎真跑一轮产出结构化摘要。
if ALERT_DRY_RUN=1 python3 -m orchestrator.run --mode heartbeat 2>/dev/null \
   | python3 -c 'import json,sys; o=sys.stdin.read(); s=json.loads(o[o.find("{"):o.rfind("}")+1]); assert s.get("mode")=="heartbeat" and "actions" in s' 2>/dev/null; then
  pass "heartbeat dry 跑通(mode+actions 结构完整)"
else
  fail "heartbeat dry 轮异常(引擎未产出结构化摘要)"
fi

echo "④ 手动配置清单覆盖 自动化+表单 两项"
grep -q "待审推卡片" docs/P2_手动配置清单.md && grep -q "表单" docs/P2_手动配置清单.md \
  && pass "清单完整" || fail "清单缺项"

echo; [ "$FAIL" -eq 0 ] && echo "✅ P5 代码侧验收通过(人测项:UI配自动化→手机点卡片闭环)" || echo "❌ P5 有失败项"
exit "$FAIL"
