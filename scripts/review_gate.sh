#!/usr/bin/env bash
# review_gate.sh — 提交前的门。**红=不留,别拿"部分绿"充数。**
#
#   bash scripts/review_gate.sh            # 快核:红线测试 + schema 契约
#   bash scripts/review_gate.sh --full     # 全量:再加 技能真源同步 + 真库冒烟 + 备份
#
# ⚠️ **门不是审查。** 审查是**每轮派子 agent**(见 docs/架构.md 第六节)——
#    "这段 if 是不是在替模型做决策""这句话是不是在骗人",只有模型答得了。
#
# ── 2026-07-14 架构审查之后重写 ──────────────────────────────────────────
#
# ★这里只留两种门:**对账** 和 **真跑**。一个"预测系统会怎么错"的检查器都不留。★
#
# 删掉了 `alignment_audit.py`(685 行机器审)。审查员逐条真跑证明它三个核心检查全是空壳:
#   · 死码检查   → 在任意 `.sh` 里加**一句注释**提到那个函数名,它就绿了
#   · 死配置检查 → 在任意 `.py` 里加**一句注释**提到那个 env 名,它就绿了
#   · 悬空引用   → 6 个已删模块只盖到 2 个
# 而且它**自己** import 了已删的模块 —— 那一刻机器审根本不设防。
#
# 我随后写了个 `check_dangling.py` 想替代它 —— **那是同一个病的第三次**:
# 一份硬编码的"已删清单",既是"世界有什么"的第二份真源(一改必漏),
# 又是"我预测系统会怎么错"。它自己第一版就是空壳(漏了 `from X import Y` 这种形态)。**也删了。**
#
# **审查的主力是子 agent**(docs/架构.md 第六节):
#   机械检查器永远查不出「这段 if 是不是在替模型做决策」「这句 docstring 是不是在骗人」——
#   **那只有模型能回答。** 今天三个子 agent 审出了三个红线洞,机器审一个都没抓到。
#
# 机器只做它真做得了的事:**跟活库对账、跟 GitHub 对账、真跑一次**。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
export LARK_CLI_NO_PROXY=1
PY=python3
FULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1;;
    *) echo "未知参数: $1"; exit 2;;
  esac
  shift
done

RED=0
hr(){ printf '─%.0s' $(seq 1 60); echo; }
gate(){ local name="$1"; shift
  if "$@" >/tmp/rg_$$.log 2>&1; then echo "  ✓ $name"
  else echo "  ✗ $name"; tail -8 /tmp/rg_$$.log | sed 's/^/      /'; RED=1; fi
  rm -f /tmp/rg_$$.log; }

echo "══════ 门 ($(git branch --show-current) @ $(git rev-parse --short HEAD)) ══════"

# ── ① 红线(唯一保留的测试。**每一条都过了"把 bug 塞回去,看它报不报"**)──
hr; echo "① 红线测试"
gate "pytest tests/(只测红线:门装没装在门框上 · 阈值有没有旋钮 · 状态能不能被改成已发 · …)" \
     $PY -m pytest tests/ -q

# ── ② schema 契约(代码消费的字段/枚举 ⊆ 活库)────────────────────────
hr; echo "② schema 契约(代码 vs 活 Base)"
gate "check_schema_drift(真库只读)" $PY scripts/check_schema_drift.py

if [ "$FULL" = "1" ]; then
  # ── ③ 技能真源同步 ──────────────────────────────────────────────────
  # install_skills.sh 会把技能仓 checkout 到锁定 sha → **HEAD 游离**。
  # 这时 commit 落在游离 HEAD 上,`git push origin main` **静默无操作,退出码 0**。
  # 所以只有一条自证:**直接问 GitHub**(本地 HEAD 和本地 origin/main 缓存都会骗你)。
  # ⚠️ **每一个源都要对**(2026-07-14:挂上 video-engine 之后,这道门差点只查第一个源)
  # `sources` 是数组:qiaohe-skill(出稿/打标/选材…)+ video-engine(分镜/previz/精剪)。
  # 只查 sources[0] = **第二个源的技能可以随便漂移,门一声不吭**。
  hr; echo "③ 技能真源同步(**每个源**的 sha == GitHub 上的 main?)"
  gate "所有源的 lock sha == 远端 main(直接问 GitHub)" bash -c '
    n=$(python3 -c "import json;print(len(json.load(open(\"skills.lock.json\"))[\"sources\"]))")
    for i in $(seq 0 $((n-1))); do
      name=$(python3 -c "import json;print(json.load(open(\"skills.lock.json\"))[\"sources\"][$i][\"name\"])")
      repo=$(python3 -c "import json;print(json.load(open(\"skills.lock.json\"))[\"sources\"][$i].get(\"repo\",\"\"))")
      lock=$(python3 -c "import json;print(json.load(open(\"skills.lock.json\"))[\"sources\"][$i][\"sha\"])")
      [ -n "$repo" ] || { echo "  · $name: 没有 repo(本地源),跳过"; continue; }
      remote=""
      for t in 1 2 3; do remote=$(git ls-remote "$repo" refs/heads/main 2>/dev/null | cut -f1); [ -n "$remote" ] && break; done
      [ -n "$remote" ] || { echo "  ✗ $name: 问不到 GitHub —— **不能证实就不能放行**"; exit 1; }
      [ "$lock" = "$remote" ] || { echo "  ✗ $name: lock=${lock:0:8} 远端=${remote:0:8} → **服务器会装到另一份技能**"; exit 1; }
      echo "  ✓ $name: ${remote:0:8}"
    done'

  # ── ④ 真跑冒烟(零 mock,真测试库:**agent 的眼睛真的睁得开吗**)────────
  hr; echo "④ 真跑冒烟(真库)"
  gate "python3 -m orchestrator board(退出0 且看得见红线+账号)" bash -c \
    "$PY -m orchestrator board > /tmp/b_\$\$.out 2>&1 && grep -q 红线 /tmp/b_\$\$.out && grep -q 账号 /tmp/b_\$\$.out; rc=\$?; rm -f /tmp/b_\$\$.out; exit \$rc"

  # ── ⑤ 备份(**它救过命** —— 别再让它断)──────────────────────────────
  # 2026-07-14:一次 select 字段 PUT 把 280 行的『类型』全抹空(飞书返回 code=0,毫无报错)。
  # 救回来靠的就是 backups/。而那天之后 cron 被卸光、CLI 里没有 backup 动词、门也不跑它 ——
  # **从那时起没有任何东西在备份**。任何 schema 级操作之前,库里得有一份昨天的自己。
  hr; echo "⑤ 备份(schema 操作抹掉过 280 行,是它救回来的)"
  gate "backup_tables(全表 dump 进 backups/)" $PY scripts/backup_tables.py
else
  hr; echo "③④⑤ 全量门:跳过(加 --full 跑 技能真源同步 + 真库冒烟 + 备份;交付前必跑)"
fi

hr
if [ "$RED" = "0" ]; then
  echo "✅ 门全绿。"
  [ "$FULL" = "0" ] && echo "   (交付前记得再跑一次 --full)"
else
  echo "❌ 有门红了(见上✗)。先修红再谈推进,红=不留。"
fi

# ── 架构自问(**不判断,只提问**)────────────────────────────────────────
# 机械检查器永远查不出「这段 if 是不是在替模型做决策」—— 那只有模型能回答。
bash "$ROOT/scripts/ask.sh"

exit $RED
