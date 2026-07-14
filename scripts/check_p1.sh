#!/usr/bin/env bash
# check_p1.sh — P1 基地骨架验收脚本(issue #2)。任何一项失败 exit 非零。
# 用法: bash scripts/check_p1.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAIL=1; }

# ── ① skills.lock.json 可解析且 local 路径存在 ──────────────────────
#    (删了原①「AGENTS.md 含 14 个生产 table_id」:它检查的是**文档里有没有这些字符串**,
#     不是任何行为;而且内容是**生产库**的表 ID —— 生产库焊死不碰,把它列在文档里
#     毫无用处,**还诱导人去碰它**。2026-07-14)
echo "② skills.lock.json 可解析 + sources.local 存在"
if [ ! -f skills.lock.json ]; then
  fail "skills.lock.json 不存在"
else
  if OUT=$(python3 - <<'PY' 2>&1
import json, os, sys
sys.path.insert(0, ".")
from orchestrator import skills_lock
lock = json.loads(open("skills.lock.json").read())
errs = skills_lock.validate(lock)                 # 结构语义:远程须 repo+40位sha;本地 sha='local' 免 repo
for s in lock["sources"]:                          # 部署校验:local 路径须存在
    local = os.path.expanduser(s["local"])
    if not os.path.isdir(local):
        errs.append(f"local 路径不存在: {local}")
assert not errs, "; ".join(errs)
srcs = lock["sources"]
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

echo; [ "$FAIL" -eq 0 ] && echo "✅ P1 验收全部通过" || echo "❌ 有失败项"
exit "$FAIL"
