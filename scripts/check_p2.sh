#!/usr/bin/env bash
# check_p2.sh — P2 测试 Base 改造验收脚本(issue #3)。任何一项失败 exit 非零。
# 用法: bash scripts/check_p2.sh
# 只读:全部检查项对 Base 零写入(lark-cli 只用 field-list / record-list)。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export LARK_CLI_NO_PROXY=1

TEST_BASE="ZhzJbfkOsafwevsWkW8cfoILnfb"   # 测试 Base(唯一可写);生产 N9IVbi… 绝不触碰

FAIL=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAIL=1; }

# 表名 → 测试 Base table_id(按名解析,不硬编码;来源 schema/test/_tables.json)
tid() {
  python3 -c "import json,sys; print(json.load(open('schema/test/_tables.json'))['tables'][sys.argv[1]])" "$1" 2>/dev/null
}

# ── ① 改造前快照存在 ────────────────────────────────────────────────
echo "① schema/snapshots/test-改造前-*/ 快照存在且含 14 表"
SNAP_DIR=$(ls -d schema/snapshots/test-改造前-* 2>/dev/null | sort | tail -1)
if [ -z "${SNAP_DIR:-}" ]; then
  fail "找不到 schema/snapshots/test-改造前-<日期>/"
else
  NT=$(find "$SNAP_DIR" -maxdepth 1 -name '*.json' ! -name '_tables.json' | wc -l | tr -d ' ')
  if [ "$NT" -eq 14 ] && [ -f "$SNAP_DIR/_tables.json" ]; then
    pass "$SNAP_DIR (14 表 + _tables.json)"
  else
    fail "$SNAP_DIR 表 json = $NT (应为 14) 或缺 _tables.json"
  fi
fi

# ── ② 笔记表「状态」含全部目标枚举(活表实测) ──────────────────────
echo "② 笔记表「状态」单选含全部 9 个目标枚举(测试 Base 活表)"
NOTE_TID=$(tid 笔记表)
if [ -z "${NOTE_TID:-}" ]; then
  fail "schema/test/_tables.json 解析不到 笔记表 table_id"
else
  OPTS=$(lark-cli base +field-list --base-token "$TEST_BASE" --table-id "$NOTE_TID" --as bot \
    -q '.data.fields[] | select(.name=="状态") | .options[].name' 2>/dev/null | tr -d '"')
  MISSING=()
  for o in 想法储备 待拍素材 待出文案 草稿待发 已批准 待发布 已发 已回流 暂缓归档; do
    echo "$OPTS" | grep -qx "$o" || MISSING+=("$o")
  done
  if [ ${#MISSING[@]} -eq 0 ]; then
    pass "状态枚举 9/9 全在(含新增 已批准/待发布/已回流)"
  else
    fail "状态缺枚举: ${MISSING[*]}"
  fi
fi

# ── ③ 笔记表「AI声明」字段存在且为 checkbox(活表实测) ─────────────
echo "③ 笔记表「AI声明」字段存在且 type=checkbox"
if [ -n "${NOTE_TID:-}" ]; then
  T=$(lark-cli base +field-list --base-token "$TEST_BASE" --table-id "$NOTE_TID" --as bot \
    -q '.data.fields[] | select(.name=="AI声明") | .type' 2>/dev/null | tr -d '"')
  if [ "$T" = "checkbox" ]; then
    pass "AI声明 = checkbox"
  else
    fail "AI声明 缺失或类型不对(实测: '${T:-<无>}')"
  fi
else
  fail "笔记表 table_id 未解析,跳过"
fi

# ── ④ 账号表 = 4 条记录且含 4 个账号标识(活表实测) ─────────────────
echo "④ 账号表 4 条记录,含 4 个小红书账号标识"
ACC_TID=$(tid 账号表)
if [ -z "${ACC_TID:-}" ]; then
  fail "schema/test/_tables.json 解析不到 账号表 table_id"
else
  RAW=$(lark-cli base +record-list --base-token "$TEST_BASE" --table-id "$ACC_TID" --as bot 2>/dev/null)
  NREC=$(echo "$RAW" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']['record_id_list']))" 2>/dev/null)
  if [ "${NREC:-0}" -eq 4 ]; then
    pass "账号表记录数 = 4"
  else
    fail "账号表记录数 = ${NREC:-?} (应为 4)"
  fi
  MISSING=()
  for acc in 63068651425 26507264096 60befdfd000000000101cc10 巧荷·东方美学; do
    echo "$RAW" | grep -q "$acc" || MISSING+=("$acc")
  done
  if [ ${#MISSING[@]} -eq 0 ]; then
    pass "4 个账号标识全在(63068651425 / 26507264096 / 60befdfd… / 官号@巧荷·东方美学)"
  else
    fail "账号表缺标识: ${MISSING[*]}"
  fi
fi

# ── ⑤ schema_diff 对齐探针:只有受控新增/删除,零改名 ───────────────
echo "⑤ scripts/schema_diff.py 断言通过(改造前快照 vs schema/test/)"
if [ -z "${SNAP_DIR:-}" ]; then
  fail "无快照可比,跳过"
elif OUT=$(python3 scripts/schema_diff.py "$SNAP_DIR" schema/test --assert-p2 2>&1); then
  pass "schema_diff 断言通过"
  echo "$OUT" | sed 's/^/    /'
else
  fail "schema_diff 断言失败:"
  echo "$OUT" | sed 's/^/    /'
fi

# ── ⑥ MIGRATION_P2.md 存在且非空 ───────────────────────────────────
echo "⑥ docs/MIGRATION_P2.md 存在且非空"
if [ -s docs/MIGRATION_P2.md ]; then
  pass "docs/MIGRATION_P2.md ($(wc -l < docs/MIGRATION_P2.md | tr -d ' ') 行)"
else
  fail "docs/MIGRATION_P2.md 缺失或为空"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ P2 验收全部通过"
else
  echo "❌ P2 验收有失败项"
fi
exit "$FAIL"
