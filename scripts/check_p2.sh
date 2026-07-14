#!/usr/bin/env bash
# check_p2.sh — 测试库健康门(lean)。大刀阔斧后只留薄执行器 A 真正依赖的活表事实:
#   ② 笔记表「状态」含全部目标枚举(尤其 草稿待发)  ③ 笔记表「AI声明」= checkbox(红线载体)
#   ④ 账号表 4 条 + 4 个账号标识
# 已砍(交接文档 §5):① 改造前 14 表快照、⑤ schema_diff 改造前契约锁、⑥ MIGRATION_P2 —— 它们把
# 测试库钉在改造前 schema、挡住 base 瘦身;瘦身期漂移检测改用 dump_schema + git diff schema/test。
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

# ── ② 笔记表「状态」含全部目标枚举(活表实测;薄执行器写「草稿待发」必须在册) ──────
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
    pass "状态枚举 9/9 全在(含薄执行器落点 草稿待发)"
  else
    fail "状态缺枚举: ${MISSING[*]}"
  fi
fi

# ── ③ 笔记表「AI声明」字段存在且为 checkbox(红线载体:人勾 AI 声明) ────────────
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

# ── ④ 账号表 = 3 条记录且含 3 个账号标识(活表实测;官号 2026-07-14 下线)──
echo "④ 账号表 4 条记录,含 4 个小红书账号标识"
ACC_TID=$(tid 账号表)
if [ -z "${ACC_TID:-}" ]; then
  fail "schema/test/_tables.json 解析不到 账号表 table_id"
else
  RAW=$(lark-cli base +record-list --base-token "$TEST_BASE" --table-id "$ACC_TID" --as bot 2>/dev/null)
  NREC=$(echo "$RAW" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']['record_id_list']))" 2>/dev/null)
  if [ "${NREC:-0}" -eq 3 ]; then
    pass "账号表记录数 = 4"
  else
    fail "账号表记录数 = ${NREC:-?} (应为 3)"
  fi
  MISSING=()
  for acc in 63068651425 26507264096 60befdfd000000000101cc10; do
    echo "$RAW" | grep -q "$acc" || MISSING+=("$acc")
  done
  if [ ${#MISSING[@]} -eq 0 ]; then
    pass "3 个账号标识全在(63068651425 / 26507264096 / 60befdfd…)"
  else
    fail "账号表缺标识: ${MISSING[*]}"
  fi
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 测试库健康门(lean)通过"
else
  echo "❌ 测试库健康门有失败项"
fi
exit "$FAIL"
