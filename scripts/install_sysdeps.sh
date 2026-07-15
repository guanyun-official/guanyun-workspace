#!/usr/bin/env bash
# 装 media.py 依赖的系统二进制(Linux)。幂等:已装则跳过。
#
# 这是 harness 的「手」长齐必需的底层工具 —— orchestrator/media.py 里:
#   ffprobe / ffmpeg :视频时长 + 抽帧(video_frames)
#   heif-convert     :iPhone 实况(livp)/ heic 静图 → jpg(libheif-examples)
#   convert          :通用静图转码兜底(ImageMagick,需带 heic delegate 更佳)
# mac 上 sips 自带,heif-convert/convert 不必要;ffmpeg 走 brew install ffmpeg。
#
# 不归在这里装的(各自有脚本/人工):
#   lark-cli / BaiduPCS-Go / hermes / Python deps(pip) / 视频引擎(setup.sh)
set -euo pipefail

if [ "$(uname -s)" != "Linux" ]; then
  echo "ℹ️  非 Linux(mac 用 brew install ffmpeg;sips 自带 heic 转码)。跳过。"
  exit 0
fi

# 需要 root 才能 apt install;没有 sudo 时提示人工装。
HAS_SUDO=0
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  HAS_SUDO=1
fi

PKGS=()
need() { command -v "$1" >/dev/null 2>&1 || PKGS+=("$2"); }
need ffmpeg        ffmpeg            # 提供 ffmpeg + ffprobe
need heif-convert  libheif-examples  # heic/livp → jpg 首选
need convert       imagemagick       # 通用兜底(建议版 ≥6:6.9 带 heic delegate)

if [ ${#PKGS[@]} -eq 0 ]; then
  echo "✅ media.py 的系统依赖都齐了(ffmpeg/ffprobe/heif-convert/convert)"
  exit 0
fi

echo "缺包:${PKGS[*]}"
if [ "$HAS_SUDO" -eq 1 ]; then
  echo "→ sudo apt-get install ${PKGS[*]}"
  sudo apt-get update -qq
  sudo apt-get install -y "${PKGS[@]}"
  echo "✅ 装好。"
else
  echo "❌ 本脚本无 sudo。请人工执行(Debian/Ubuntu):"
  echo "   sudo apt-get update && sudo apt-get install -y ${PKGS[*]}"
  exit 1
fi
