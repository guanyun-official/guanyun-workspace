#!/usr/bin/env bash
# check_p3.sh — P3 技能整备验收(issue #4)。零写入:只读检查+--help 冒烟。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
QS="$HOME/Githubs/qiaohe-skill"
FAIL=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAIL=1; }

echo "① qiaohe-skill 零硬编码 Base/表 ID"
HITS=$(grep -rEn "N9IVbi6pTatJG5sqyTTcc0vSn4g|ZhzJbfkOsafwevsWkW8cfoILnfb|tbl[A-Za-z0-9]{8,}" \
  --include="*.md" "$QS" 2>/dev/null | grep -v "示例占位" | wc -l | tr -d ' ')
[ "$HITS" -eq 0 ] && pass "残留硬编码 = 0" || fail "仍有 $HITS 处硬编码 ID"

echo "② marketplace.json 合法且带 version"
V=$(python3 -c "import json;print(json.load(open('$QS/.claude-plugin/marketplace.json'))['plugins'][0]['version'])" 2>/dev/null)
[ -n "${V:-}" ] && pass "marketplace version = $V" || fail "marketplace.json 缺失/非法/无 version"

echo "③ 4 个迁入技能存在且带 SKILL.md"
MISSING=()
for s in explosive-teardown account-teardown topic-deepening xhs-collector; do
  [ -f "$QS/$s/SKILL.md" ] || MISSING+=("$s")
done
[ ${#MISSING[@]} -eq 0 ] && pass "explosive/account-teardown/topic-deepening/xhs-collector 全在" || fail "缺: ${MISSING[*]}"

echo "④ skills.lock 与 qiaohe-skill HEAD 一致且含 18 技能"
python3 - "$QS" <<'PY' && pass "lock 对齐" || fail "lock 漂移(sha 或技能数)"
import json,subprocess,sys
d=json.load(open('skills.lock.json'))
src=[s for s in d['sources'] if 'qiaohe' in s['name']][0]
head=subprocess.run(['git','-C',sys.argv[1],'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
assert src['sha']==head, f"sha {src['sha'][:8]} != HEAD {head[:8]}"
assert len(src['skills'])>=18
PY

echo "⑤ install 后 skills/ ≥21"
N=$(find skills -maxdepth 1 -mindepth 1 | wc -l | tr -d ' ')
[ "$N" -ge 21 ] && pass "skills/ = $N" || fail "skills/ = $N (<21)"

echo "⑥ symlink 下 lib 三级定位冒烟(不带 env)"
if env -u GY_WORKSPACE_ROOT python3 skills/explosive-teardown/scripts/check_firewall.py --help >/dev/null 2>&1; then
  pass "check_firewall.py --help 经 symlink 找到 lib"
else
  fail "symlink 冒烟失败(lib 定位断)"
fi

echo "⑦ 注入解析可用(表名→ID)"
TID=$(python3 -c "import json;print(json.load(open('schema/test/_tables.json'))['tables']['目标客户'])" 2>/dev/null)
[ -n "${TID:-}" ] && pass "目标客户 → $TID(落库写删已于 2026-07-08 实测)" || fail "schema/test/_tables.json 解析失败"

echo
[ "$FAIL" -eq 0 ] && echo "✅ P3 验收全部通过" || echo "❌ P3 验收有失败项"
exit "$FAIL"
