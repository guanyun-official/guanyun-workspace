#!/usr/bin/env bash
# check_p1.sh — P1 基地骨架验收脚本(issue #2)。任何一项失败 exit 非零。
# 用法: bash scripts/check_p1.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAIL=1; }

# ── ① AGENTS.md 包含全部 14 个生产 table_id ──────────────────────────
echo "① AGENTS.md 含全部 14 个生产 table_id"
PROD_TABLE_IDS=(
  tbl2ZnYoLX3d0QtE  # 衣服总表
  tblveO3Wzm3Foo6v  # 账号表
  tblWZgMpWNqfHabt  # 内容类型表
  tbljjcr9gLk7cPbn  # 面料·工艺库
  tbles5eiDykCBxD1  # 素材表
  tblHi1Htg5wntydY  # 笔记表
  tblaiG8bQumH5CQW  # 关键词库
  tblM6EDqDdcPYIxO  # 目标客户
  tblP4jlRNZGCiIU2  # 灵感库
  tblSidOqOT1B4dj9  # 技能表
  tblcvycKVdY3IF7A  # Issue 表
  tbleWyxtJD57a59X  # 修订日志
  tblj8q46icA5YZoM  # 素人推广案例
  tblgZRFvZiZtfxNN  # 运行日志表
)
if [ ! -f AGENTS.md ]; then
  fail "AGENTS.md 不存在"
else
  MISSING=()
  for tid in "${PROD_TABLE_IDS[@]}"; do
    grep -q "$tid" AGENTS.md || MISSING+=("$tid")
  done
  if [ ${#MISSING[@]} -eq 0 ]; then
    pass "14/14 table_id 全部在 AGENTS.md"
  else
    fail "AGENTS.md 缺 table_id: ${MISSING[*]}"
  fi
fi

# ── ② skills.lock.json 可解析且 local 路径存在 ──────────────────────
echo "② skills.lock.json 可解析 + sources.local 存在"
if [ ! -f skills.lock.json ]; then
  fail "skills.lock.json 不存在"
else
  if OUT=$(python3 - <<'PY' 2>&1
import json, os, sys
lock = json.load(open("skills.lock.json"))
srcs = lock["sources"]
assert isinstance(srcs, list) and srcs, "sources 为空"
for s in srcs:
    for k in ("name", "repo", "local", "ref", "sha", "skills", "install"):
        assert k in s, f"source {s.get('name','?')} 缺键 {k}"
    local = os.path.expanduser(s["local"])
    assert os.path.isdir(local), f"local 路径不存在: {local}"
print("sources=%d skills=%d" % (len(srcs), sum(len(s["skills"]) for s in srcs)))
PY
  ); then
    pass "skills.lock.json OK ($OUT)"
  else
    fail "skills.lock.json 解析/校验失败: $OUT"
  fi
fi

# ── ③ install_skills.sh 跑完后 skills/ 下技能数 ≥17 ─────────────────
echo "③ install_skills.sh 幂等安装,skills/ 技能数 ≥17"
if [ ! -f scripts/install_skills.sh ]; then
  fail "scripts/install_skills.sh 不存在"
else
  if bash scripts/install_skills.sh >/dev/null 2>&1; then
    N=$(find skills -mindepth 1 -maxdepth 1 \( -type d -o -type l \) 2>/dev/null | wc -l | tr -d ' ')
    if [ "${N:-0}" -ge 17 ]; then
      pass "skills/ 下技能数 = $N (≥17)"
    else
      fail "skills/ 下技能数 = ${N:-0} (<17)"
    fi
  else
    fail "install_skills.sh 运行失败"
  fi
fi

# ── ④ lib 冒烟 import ────────────────────────────────────────────────
echo "④ PYTHONPATH=lib import 冒烟"
if OUT=$(PYTHONPATH=lib python3 -c "import feishu_workbench,xhs_fetch,brand_kb,skill_gate,skill_io; print('ok')" 2>&1); then
  pass "import feishu_workbench,xhs_fetch,brand_kb,skill_gate,skill_io"
else
  fail "lib import 失败: $OUT"
fi

# ── ⑤ .mcp.json JSON 合法 ────────────────────────────────────────────
echo "⑤ .mcp.json JSON 合法"
if [ -f .mcp.json ] && python3 -c "import json; json.load(open('.mcp.json'))" 2>/dev/null; then
  pass ".mcp.json 合法"
else
  fail ".mcp.json 缺失或非法 JSON"
fi

# ── ⑥ schema/prod/ 存在 14 个表 json ────────────────────────────────
echo "⑥ schema/prod/ 14 个表契约 + _tables.json"
if [ ! -d schema/prod ]; then
  fail "schema/prod/ 不存在"
else
  NT=$(find schema/prod -maxdepth 1 -name '*.json' ! -name '_tables.json' | wc -l | tr -d ' ')
  if [ "$NT" -eq 14 ] && [ -f schema/prod/_tables.json ]; then
    pass "schema/prod/ 表 json = $NT + _tables.json"
  else
    fail "schema/prod/ 表 json = $NT (应为 14),_tables.json $([ -f schema/prod/_tables.json ] && echo 在 || echo 缺)"
  fi
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ P1 验收全部通过"
else
  echo "❌ P1 验收有失败项"
fi
exit "$FAIL"
