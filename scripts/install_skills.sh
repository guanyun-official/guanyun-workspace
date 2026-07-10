#!/usr/bin/env bash
# install_skills.sh — 按 skills.lock.json 把技能 symlink 进本仓库 skills/(幂等,可重复跑)。
# skills/ 已在 .gitignore;升级技能 = 改 lock 的 sha → 重跑本脚本。
# 用法: bash scripts/install_skills.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/skills.lock.json"
DEST="$ROOT/skills"

[ -f "$LOCK" ] || { echo "❌ 缺 $LOCK" >&2; exit 1; }
mkdir -p "$DEST"

# 解析 lock:每行 "name<TAB>local<TAB>sha<TAB>skill"
python3 - "$LOCK" <<'PY' | while IFS=$'\t' read -r name local sha skill; do
import json, sys
lock = json.load(open(sys.argv[1]))
for s in lock["sources"]:
    if s.get("install") != "symlink":
        raise SystemExit(f"未支持的 install 模式: {s.get('install')} (source={s['name']})")
    for sk in s["skills"]:
        print("\t".join([s["name"], s["local"], s["sha"], sk]))
PY
  src_root="${local/#\~/$HOME}"
  # 技能目录探测:仓库根 <local>/<skill> 或 <local>/skills/<skill>
  if [ -d "$src_root/$skill" ]; then
    src="$src_root/$skill"
  elif [ -d "$src_root/skills/$skill" ]; then
    src="$src_root/skills/$skill"
  else
    echo "❌ [$name] 技能不存在: $skill(找过 $src_root/{,skills/}$skill)" >&2
    exit 1
  fi
  [ -f "$src/SKILL.md" ] || { echo "❌ [$name] $skill 缺 SKILL.md" >&2; exit 1; }
  # 远程 source 才做 SHA 漂移警告；workspace-native source 用 sha=local 显式标记。
  if [ "$sha" != "local" ]; then
    head="$(git -C "$src_root" rev-parse HEAD 2>/dev/null || echo unknown)"
    if [ "$head" != "$sha" ]; then
      echo "  ⚠ [$name] 本地 HEAD=$head ≠ lock sha=$sha(考虑更新 skills.lock.json)" >&2
    fi
  fi
  ln -sfn "$src" "$DEST/$skill"
  echo "  ✓ skills/$skill → $src"
done

N=$(find "$DEST" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) | wc -l | tr -d ' ')
echo "✅ 安装完成:skills/ 下技能数 = $N"
