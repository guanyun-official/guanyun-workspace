#!/usr/bin/env bash
# review_gate.sh — 停止前一条命令『审查产物 + verify + 列还能推什么』(反"莫名其妙停")。
#
#   bash scripts/review_gate.sh            # 快核:keep门(pytest+ar_check)+产物审查+开口项扫描
#   bash scripts/review_gate.sh --full     # 全量:再加 check_p1-6 + verify_usable 综合验收(慢,~3min)
#   bash scripts/review_gate.sh --since <git-ref>   # 产物审查对比基准(默认上一个 tag 或 HEAD~5)
#
# 退出码:任一 keep 门红 = 非0(是闸不是报告)。开口项只列不判红(供"还能推什么")。
# 设计:一次看清『产物过没过审 + 还剩什么能推』,不用再靠记忆决定停不停。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
export LARK_CLI_NO_PROXY=1
PY=python3
FULL=0; SINCE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1;;
    --since) SINCE="$2"; shift;;
    *) echo "未知参数: $1"; exit 2;;
  esac
  shift
done
[ -z "$SINCE" ] && SINCE="$(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~5)"

RED=0
hr(){ printf '─%.0s' $(seq 1 60); echo; }
gate(){ # gate <名> <命令...>:跑,绿✓红✗(红→RED=1)
  local name="$1"; shift
  if "$@" >/tmp/review_gate_$$.log 2>&1; then
    echo "  ✓ $name"
  else
    echo "  ✗ $name  —— 末尾输出:"; tail -4 /tmp/review_gate_$$.log | sed 's/^/      /'
    RED=1
  fi
  rm -f /tmp/review_gate_$$.log
}

echo "══════ 审查/verify 门 ($(git branch --show-current) @ $(git rev-parse --short HEAD)) ══════"

# ── ① keep 门(每次都跑,快核心)────────────────────────────────
hr; echo "① keep 门(硬闸,红=没过审)"
gate "pytest 全绿" $PY -m pytest -q
gate "ar_check SCORE=100" bash -c '$0 scripts/ar_check.py 2>&1 | grep -q "SCORE=100"' "$PY"

# ── ② 全量(--full 才跑:check_p + 综合验收)────────────────────
if [ "$FULL" = "1" ]; then
  hr; echo "② 全量门(dogfood 冒烟 + check_p1-6 + 综合验收 verify_usable)"
  gate "dogfood 冒烟(真库:账号名/link解析/去重键 人能看懂的真事)" $PY scripts/dogfood_smoke.py
  for s in scripts/check_p1.sh scripts/check_p2.sh scripts/check_p3.sh scripts/check_p4.sh scripts/check_p5.sh scripts/check_p6.sh; do
    [ -f "$s" ] && gate "$(basename "$s")" bash "$s"
  done
  gate "verify_usable 综合验收" $PY scripts/verify_usable.py
else
  hr; echo "② 全量门:跳过(加 --full 跑 dogfood冒烟 + check_p1-6 + verify_usable,交付前必跑)"
fi

# ── ③ 产物审查(自 $SINCE 起改了什么)──────────────────────────
hr; echo "③ 产物审查(自 $SINCE):"
echo "  提交:"; git log --oneline "$SINCE"..HEAD 2>/dev/null | sed 's/^/    /' | head -20
echo "  变更文件:"; git diff --stat "$SINCE"..HEAD 2>/dev/null | tail -12 | sed 's/^/    /'

# ── ④ 还能推什么(开口项扫描:ADR残留 + 代码TODO + 未接线)─────────
hr; echo "④ 还能推什么(开口项,只列不判红):"
echo "  ADR 里标『待/残留/follow-up/未做/未接』的项:"
grep -rn "待用户\|待 schema\|待 schema\|残留\|follow-up\|未做\|未接\|TODO\|FIXME" docs/adr/ 2>/dev/null \
  | grep -iv "已交付\|已修\|不做" | sed 's/^/    /' | head -18
echo "  代码里的 TODO/FIXME/XXX/HACK:"
grep -rn "TODO\|FIXME\|XXX\|HACK" orchestrator/ scripts/ --include="*.py" 2>/dev/null | sed 's/^/    /' | head -12
echo "  开发 issue(若有 issue-tracker):"
ls issues/ 2>/dev/null | sed 's/^/    /' | head -8 || echo "    (无 issues/ 目录)"

hr
if [ "$RED" = "0" ]; then
  echo "✅ keep 门全绿。产物过审。上面④是『还能推什么』候选——挑一个继续,别莫名停。"
  [ "$FULL" = "0" ] && echo "   (交付前记得再跑一次 --full 过 check_p + 综合验收)"
else
  echo "❌ 有门红了(见上✗)。先修红再谈推进,红=不留。"
fi
exit $RED
