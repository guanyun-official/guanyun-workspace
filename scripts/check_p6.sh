#!/usr/bin/env bash
# check_p6.sh — P6 证据验收(默认只读校验;FULL=1 重跑压测,约5分钟且动测试表)。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① 演练报告在册"
[ -s docs/P6_演练报告.md ] && grep -q "打回率 0/3" docs/P6_演练报告.md && pass "P6_演练报告.md" || fail "报告缺失/不完整"

echo "② _E2E 3 条终态=已发+AI声明(活表)"
OUT=$(python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from orchestrator import feishu_io
n = 0
for r in feishu_io.list_records("笔记表"):
    f = r["fields"]
    t = f.get("排期编号")
    if isinstance(t, list):
        t = "".join(x.get("text", "") for x in t if isinstance(x, dict))
    if str(t).startswith("_E2E-") and f.get("状态") == "已发" and f.get("AI声明") and f.get("实际发布日"):
        n += 1
print(n)
PY
)
[ "$OUT" = "3" ] && pass "3/3 已发+AI声明+发布日" || fail "活表证据 $OUT/3"

echo "③ 压测残留清零(_STRESS 前缀)"
OUT=$(python3 - <<'PY'
import sys; sys.path.insert(0, ".")
from orchestrator import feishu_io
print(sum(1 for r in feishu_io.list_records("笔记表")
          if "_STRESS" in str(r["fields"].get("排期编号"))))
PY
)
[ "$OUT" = "0" ] && pass "零残留" || fail "残留 $OUT 条"

echo "④ 单测回归(engine 修复后)"
python3 -m unittest discover -s tests 2>&1 | grep -q "^OK" && pass "unittest OK" || fail "单测失败"

if [ "${FULL:-0}" = "1" ]; then
  echo "⑤ FULL:重跑压测 4 场景"
  ALERT_DRY_RUN=1 python3 scripts/stress_p6.py >/tmp/gy_stress.log 2>&1 \
    && pass "压测全过" || { fail "压测失败"; tail -5 /tmp/gy_stress.log; }
fi

echo; [ "$FAIL" -eq 0 ] && echo "✅ P6 验收通过" || echo "❌ P6 有失败项"
exit "$FAIL"
