#!/usr/bin/env bash
# review_gate.sh — 停止前一条命令『审查产物 + verify + 列还能推什么』(反"莫名其妙停")。
#
#   bash scripts/review_gate.sh            # 快核:①②③(红线测试 + schema 契约 + 机器审)
#   bash scripts/review_gate.sh --full     # 全量:再加 ④ 真库冒烟(python3 -m orchestrator board)
#   bash scripts/review_gate.sh --since <git-ref>   # 产物审查对比基准(默认上一个 tag 或 HEAD~5)
#
# 退出码:任一门红 = 非0(是闸不是报告)。产物审查/开口项只列不判红(供"还能推什么")。
#
# 2026-07-14 重写:老版本的门(ar_check/verify_usable/dogfood_smoke/check_p1-6)断言的正是
# 刚拆掉的导轨(cadence 轮转、draft_one 干跑、sourcing 三态……)。CLAUDE.md 的纪律是
# "只写红线,别测判断、别测措辞"——所以新的门只留下**真能拦住事故**的四道:
#   ① 红线测试(pytest tests/) ② schema 契约(代码 ⊆ 活库) ③ 机器审(死码/死配置/悬空引用/空门)
#   ④ 真跑冒烟(零 mock,agent 的眼睛真的睁得开吗)
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
    echo "  ✗ $name  —— 末尾输出:"; tail -8 /tmp/review_gate_$$.log | sed 's/^/      /'
    RED=1
  fi
  rm -f /tmp/review_gate_$$.log
}

echo "══════ 审查/verify 门 ($(git branch --show-current) @ $(git rev-parse --short HEAD)) ══════"

# ── ① 红线测试(每次都跑,快核心)────────────────────────────
hr; echo "① 红线测试(硬闸,红=没过审)"
gate "pytest tests/ 全绿(只测红线,不测判断)" $PY -m pytest tests/ -q

# ── ② schema 契约(代码消费的字段/枚举 ⊆ 活库,真库只读)──────────
hr; echo "② schema 契约(代码 vs 活 Base,读侧漂移探针)"
gate "check_schema_drift(真库只读)" $PY scripts/check_schema_drift.py

# ── ③ 机器审(死码/死配置/悬空引用/空门,10 种病里机械可查的那几种)──
hr; echo "③ 机器审 alignment_audit(死码/死配置/悬空引用/空门)"
gate "alignment_audit" $PY scripts/alignment_audit.py

# ── ③b 技能真源同步(2026-07-14 真栽过:**push 静默无操作**)────────────
# install_skills.sh 会把技能仓 checkout 到锁定 sha → **HEAD 游离**。
# 之后在技能仓 commit,提交落在游离 HEAD 上;`git push origin main` 推的是
# **还停在旧 sha 的 main 分支** —— 静默无操作,退出码 0。
# 于是"改完 push"这条纪律在这种状态下**无法执行,而且不报错**。
# 所以门必须**直接问 GitHub**:lock 的 sha == 远端 main?
# (不是本地 HEAD、不是本地 origin/main 缓存 —— 那两个都会骗你。)
# 服务器上的 agent 只从 GitHub 装技能。**sha 对不上 = 它跑的不是我们这份。**
hr; echo "③b 技能真源同步(skills.lock.json 的 sha == GitHub 上的 main?)"
gate "lock sha == 远端 main(直接问 GitHub,不信本地缓存)" bash -c '
  set -e
  repo=$(python3 -c "import json;print(json.load(open(\"skills.lock.json\"))[\"sources\"][0][\"repo\"])")
  lock=$(python3 -c "import json;print(json.load(open(\"skills.lock.json\"))[\"sources\"][0][\"sha\"])")
  remote=$(git ls-remote "$repo" refs/heads/main | cut -f1)
  [ -n "$remote" ] || { echo "问不到远端 main"; exit 1; }
  [ "$lock" = "$remote" ] || { echo "lock=$lock"; echo "远端=$remote"; echo "→ 技能没推上去(或忘了更新 lock)。服务器会装到**另一份**技能。"; exit 1; }
  echo "lock == 远端 main == $remote"'

# ── ④ 真跑冒烟(--full 才跑:零 mock,真测试库)────────────────
if [ "$FULL" = "1" ]; then
  hr; echo "④ 真跑冒烟(真库,agent 的眼睛真的睁得开吗)"
  # 唯一诚实的"能不能用"判据:board 是 agent 的眼睛(Observation)——它必须真跑得通,
  # 而且看得见法律(红线)和世界(账号)。不是 mock 同意,是真飞书数据下真结构成立。
  gate "python3 -m orchestrator board(退出0 且看得见红线+账号)" bash -c \
    "$PY -m orchestrator board > /tmp/gy_board_\$\$.out 2>&1 && grep -q 红线 /tmp/gy_board_\$\$.out && grep -q 账号 /tmp/gy_board_\$\$.out; rc=\$?; rm -f /tmp/gy_board_\$\$.out; exit \$rc"
else
  hr; echo "④ 全量门:跳过(加 --full 跑真库冒烟,交付前必跑)"
fi

# ── ⑤ 产物审查(自 $SINCE 起改了什么)──────────────────────────
hr; echo "⑤ 产物审查(自 $SINCE):"
echo "  提交:"; git log --oneline "$SINCE"..HEAD 2>/dev/null | sed 's/^/    /' | head -20
echo "  变更文件:"; git diff --stat "$SINCE"..HEAD 2>/dev/null | tail -12 | sed 's/^/    /'

# ── ⑥ 还能推什么(开口项扫描:ADR残留 + 代码TODO + 未接线)─────────
hr; echo "⑥ 还能推什么(开口项,只列不判红):"
echo "  ADR 里标『待/残留/follow-up/未做/未接』的项:"
grep -rn "待用户\|待 schema\|待 schema\|残留\|follow-up\|未做\|未接\|TODO\|FIXME" docs/adr/ 2>/dev/null \
  | grep -iv "已交付\|已修\|不做" | sed 's/^/    /' | head -18
echo "  代码里的 TODO/FIXME/XXX/HACK:"
grep -rn "TODO\|FIXME\|XXX\|HACK" orchestrator/ scripts/ --include="*.py" 2>/dev/null | sed 's/^/    /' | head -12
echo "  开发 issue(若有 issue-tracker):"
ls issues/ 2>/dev/null | sed 's/^/    /' | head -8 || echo "    (无 issues/ 目录)"

hr
if [ "$RED" = "0" ]; then
  echo "✅ 门全绿。产物过审。上面⑥是『还能推什么』候选——挑一个继续,别莫名停。"
  [ "$FULL" = "0" ] && echo "   (交付前记得再跑一次 --full 过真库冒烟)"
else
  echo "❌ 有门红了(见上✗)。先修红再谈推进,红=不留。"
fi

# ── 里程碑自问(按 CLAUDE.md 的精神)──────────────────────────────
# 它**不判断,只提问**。判断是模型的事,提问是机制的事。
# 机械检查器(regex/AST)永远查不出「这段 if 是不是在替模型做决策」——那只有模型能回答。
# 放在 exit **之前**(第一版我把它加在 exit 后面 —— 当场造了个死码,正是它要抓的病)。
bash "$ROOT/scripts/ask.sh"

exit $RED
