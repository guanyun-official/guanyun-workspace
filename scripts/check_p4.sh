#!/usr/bin/env bash
# check_p4.sh — 薄执行器(第一目标 A)验收(lean)。大刀阔斧后重引擎已删,此门只验薄执行器真能出一条草稿 + 备份可用。
# 默认干跑不写库(base 守卫兜底);写入仅限测试 Base。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
export LARK_CLI_NO_PROXY=1
FAIL=0; pass(){ echo "  ✓ $1"; }; fail(){ echo "  ✗ $1"; FAIL=1; }

echo "① 纯函数单测(guard/draft/accounts…)"
python3 -m unittest discover -s tests 2>&1 | grep -q "^OK" && pass "unittest OK" || fail "单测失败"

echo "② 薄执行器 A 干跑:ootd号 出一条草稿(few-shot 载入 + 状态=草稿待发)"
OUT=$(python3 -m scripts.draft_one --account ootd号 2>&1)
if echo "$OUT" | grep -q "few-shot载入=True" && echo "$OUT" | grep -q '"状态": "草稿待发"'; then
  pass "draft_one 干跑通(few-shot✓ 草稿待发✓)"
else
  fail "draft_one 干跑异常"; echo "$OUT" | tail -5 | sed 's/^/    /'
fi

echo "③ 备份产出 ≥5 表(误删可恢复)"
if python3 scripts/backup_tables.py >/tmp/gy_bak.log 2>&1; then
  N=$(ls backups/test-$(date +%Y%m%d)/*.json 2>/dev/null | wc -l | tr -d ' ')
  [ "$N" -ge 5 ] && pass "backups/ 下 $N 表" || fail "备份文件 $N (<5)"
else
  fail "backup_tables.py 失败"; tail -5 /tmp/gy_bak.log | sed 's/^/    /'
fi

echo; [ "$FAIL" -eq 0 ] && echo "✅ 薄执行器 A 验收通过(lean)" || echo "❌ 有失败项"
exit "$FAIL"
