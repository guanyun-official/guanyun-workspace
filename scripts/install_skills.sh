#!/usr/bin/env bash
# install_skills.sh — 按 skills.lock.json 装技能进 skills/(幂等,可重复跑)。
#
# ★ GitHub 是技能的唯一真源;本地只是缓存;lock 里的 sha 是钉子。★
#   本地没有 → **从 GitHub clone**;本地有 → **fetch**,再 checkout 到 lock 钉住的 sha。
#   于是:技能改好 → push GitHub → 更新 lock 的 sha → 任何机器(包括服务器上的 agent)
#   重跑本脚本就拿到同一份。
#
#   2026-07-14 之前它**只 symlink 本地目录,不 clone 不 fetch** ——
#   服务器上的 agent 根本没有 ~/Githubs/qiaohe-skill,装不上技能;
#   而"推到 GitHub"也没有任何东西会去拉。**真源在 GitHub 只是一句话,链路没接。**
#
#   skills/ 已在 .gitignore(它是产物,不是源)。
#   升级技能 = 在技能仓改 → push → 改 lock 的 sha → 重跑本脚本。
#
# 用法: bash scripts/install_skills.sh          # 装(按 lock 的 sha)
#       bash scripts/install_skills.sh --offline # 不联网,只用本地缓存(离线开发)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/skills.lock.json"
DEST="$ROOT/skills"
OFFLINE=0
[ "${1:-}" = "--offline" ] && OFFLINE=1

[ -f "$LOCK" ] || { echo "❌ 缺 $LOCK" >&2; exit 1; }
mkdir -p "$DEST"

# ── ① 同步每个 source 的本地缓存到 lock 钉住的 sha ────────────────────────────
python3 - "$LOCK" <<'PY' | while IFS=$'\t' read -r name repo local sha; do
import json, sys
lock = json.load(open(sys.argv[1]))
for s in lock["sources"]:
    print("\t".join([s["name"], s.get("repo", ""), s["local"], s["sha"]]))
PY
  src_root="${local/#\~/$HOME}"
  [ "$sha" = "local" ] && continue        # workspace-native source:没有远程,跳过同步

  if [ ! -d "$src_root/.git" ]; then
    if [ "$OFFLINE" = "1" ]; then
      echo "❌ [$name] 本地缓存不存在且 --offline:$src_root" >&2; exit 1
    fi
    [ -n "$repo" ] || { echo "❌ [$name] lock 里没有 repo,无法 clone" >&2; exit 1; }
    echo "  ⇣ [$name] 本地无缓存 → 从 GitHub clone:$repo"
    git clone --quiet "$repo" "$src_root"
  elif [ "$OFFLINE" = "0" ]; then
    git -C "$src_root" fetch --quiet origin || echo "  ⚠ [$name] fetch 失败(用本地缓存继续)" >&2
  fi

  head="$(git -C "$src_root" rev-parse HEAD 2>/dev/null || echo unknown)"
  if [ "$head" != "$sha" ]; then
    if git -C "$src_root" cat-file -e "$sha^{commit}" 2>/dev/null; then
      echo "  ⇄ [$name] checkout 到 lock 钉住的 sha:${sha:0:8}(原 HEAD ${head:0:8})"
      git -C "$src_root" checkout --quiet "$sha"
    else
      # **不静默**:lock 钉的 sha 在远程都找不到 → 要么没 push,要么 lock 写错了
      echo "  ⚠ [$name] lock 的 sha=${sha:0:8} 在仓库里找不到(没 push?lock 写错?)" >&2
      echo "     当前用本地 HEAD=${head:0:8} —— **跑的技能 ≠ lock 记录的那份**" >&2
    fi
  fi
done

# ── ② symlink 每个技能进 skills/ ──────────────────────────────────────────────
python3 - "$LOCK" <<'PY' | while IFS=$'\t' read -r name local skill; do
import json, sys
lock = json.load(open(sys.argv[1]))
for s in lock["sources"]:
    if s.get("install") != "symlink":
        raise SystemExit(f"未支持的 install 模式: {s.get('install')} (source={s['name']})")
    for sk in s["skills"]:
        print("\t".join([s["name"], s["local"], sk]))
PY
  src_root="${local/#\~/$HOME}"
  if [ -d "$src_root/$skill" ]; then
    src="$src_root/$skill"
  elif [ -d "$src_root/skills/$skill" ]; then
    src="$src_root/skills/$skill"
  else
    echo "❌ [$name] 技能不存在: $skill(找过 $src_root/{,skills/}$skill)" >&2
    exit 1
  fi
  [ -f "$src/SKILL.md" ] || { echo "❌ [$name] $skill 缺 SKILL.md" >&2; exit 1; }
  ln -sfn "$src" "$DEST/$skill"
  echo "  ✓ skills/$skill → $src"
done

# ── ③ **把 lock 里没有的清掉**(不只是"加",是"让 skills/ 等于 lock")────────────
#
# ★老实现只 `ln -sfn`,从不删★(2026-07-14 架构审查删了 15 个技能之后当场撞到)
# 技能仓里删掉一个技能 → `skills/` 下那条 symlink **原样留着,指向一个不存在的目录**。
# 后果:harness 扫 `skills/` 注入目录时,**模型的 system prompt 里还挂着 15 个已经不存在的技能名**
# —— 它会去加载,然后拿到一个空。**"装出来的" ≠ "锁里写的",而没有任何东西会说话。**
#
# 安装器的本分是让 `skills/` **等于** lock,不是"至少包含" lock。
WANT=$(python3 -c "import json;print(' '.join(sorted(s for src in json.load(open('$LOCK'))['sources'] for s in src['skills'])))")
for p in "$DEST"/*; do
  [ -e "$p" ] || [ -L "$p" ] || continue
  b=$(basename "$p")
  case " $WANT " in
    *" $b "*) ;;                                  # lock 里有 → 留
    *) rm -rf "$p"; echo "  ✗ 清掉 skills/$b(lock 里没有它了)";;
  esac
done

N=$(find "$DEST" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) | wc -l | tr -d ' ')
W=$(echo "$WANT" | wc -w | tr -d ' ')
[ "$N" = "$W" ] || { echo "❌ 装出来 $N 个,锁里写着 $W 个 —— **对不上就别装完**" >&2; exit 1; }
echo "✅ skills/ 下技能数 = $N == lock 里的 $W(真源=GitHub,sha 由 skills.lock.json 钉死)"

# ── ④ 同步 hermes skillhub(★agent 靠 skill_view 加载技能,读的是这一面★)────────────
#
# ★2026-07-18 血栽:技能有**两个登记面**,只登记一个 = agent 加载不到★
#   ① skills/ 目录(上面 ①②③ 管的)—— 文件层。
#   ② hermes skillhub(~/.hermes/skills/<category>/)—— **agent 真正 skill_view 读的那面**。
#      巧荷小助手(飞书网关 agent)、cron agent 出稿时,都是 skill_view(技能名) → 读这一面。
#   新技能 writing-qiaohe-zhaji 只做了 ①,②漏了 → hermes skills list 没有它 →
#   agent skill_view 加载不到 → 运营在飞书问"有没有 zhaji",小助手答"没有"。**装了=没装。**
#
#   hermes skillhub 只要目录里有 symlink 就自动发现(建了 zhaji 软链,hermes skills list 当场认)。
#   所以这一步:让 ~/.hermes/skills/qiaohe/ 的 symlink 集合 == lock 的技能集合(加缺的、删多的)。
#   —— 和 ②③ 对 skills/ 做的是同一件事,只是换到 skillhub 这一面。
#   **只在 hermes 服务器上生效**(本机/CI 没有 ~/.hermes/skills,跳过,不报错)。
HUB="${HERMES_SKILLHUB_DIR:-$HOME/.hermes/skills/qiaohe}"
if [ -d "$(dirname "$HUB")" ]; then
  mkdir -p "$HUB"
  for sk in $WANT; do
    ln -sfn "$DEST/$sk" "$HUB/$sk"          # 指向 skills/ 那份(它再指向仓)——和现有 11 个同款
  done
  for p in "$HUB"/*; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    b=$(basename "$p")
    case " $WANT " in *" $b "*) ;; *) rm -f "$p"; echo "  ✗ skillhub 清掉 $b(lock 里没有了)";; esac
  done
  HN=$(find "$HUB" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) | wc -l | tr -d ' ')
  [ "$HN" = "$W" ] || { echo "❌ skillhub 装出 $HN 个,锁里 $W 个 —— 两面没对齐" >&2; exit 1; }
  echo "✅ hermes skillhub($HUB)技能数 = $HN == lock 的 $W —— 两面已对齐,agent skill_view 加载得到"
else
  echo "  (非 hermes 机器,跳过 skillhub 同步)"
fi
