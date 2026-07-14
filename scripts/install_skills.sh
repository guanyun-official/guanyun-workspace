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

N=$(find "$DEST" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) | wc -l | tr -d ' ')
echo "✅ 安装完成:skills/ 下技能数 = $N(真源=GitHub,本地是缓存,sha 由 skills.lock.json 钉死)"
