#!/usr/bin/env bash
# check_p6.sh — 回归+版本证据(lean)。大刀阔斧后去掉 _E2E 活表证据/压测(随重引擎删);
# 留单测 + 精简痛点基线 + skills.lock 三条护栏。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
export LARK_CLI_NO_PROXY=1
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① 单测回归"
python3 -m unittest discover -s tests 2>&1 | grep -q "^OK" && pass "unittest OK" || fail "单测失败"

echo "② 精简痛点基线 SCORE=100"
if python3 scripts/ar_check.py 2>/dev/null | grep -q "SCORE=100"; then
  pass "ar_check SCORE=100"
else
  fail "ar_check 未满分"
fi

echo "③ skills.lock 锁清单在册"
[ -s skills.lock.json ] && pass "skills.lock.json" || fail "skills.lock 缺失"

echo; [ "$FAIL" -eq 0 ] && echo "✅ 回归+版本验收通过(lean)" || echo "❌ 有失败项"
exit "$FAIL"
