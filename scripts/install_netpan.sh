#!/usr/bin/env bash
# 装 BaiduPCS-Go(netpan real 的运行依赖;「媒体唯一真身仓=网盘」 / EPIC #40)。
# 幂等:已装则跳过。mac=brew;Linux 服务器=brew(若有)否则下 GitHub release。
# 装完仍需**人工**一次:  BaiduPCS-Go login -bduss=<你的BDUSS>   (凭证人工,机器不碰)
set -euo pipefail

BIN_NAMES=(BaiduPCS-Go baidupcs-go)
for b in "${BIN_NAMES[@]}"; do
  if command -v "$b" >/dev/null 2>&1; then
    echo "✅ 已装:$(command -v "$b")  ($("$b" --version 2>/dev/null | head -1))"
    echo "   下一步(人工一次):$b login -bduss=<你的BDUSS>"
    exit 0
  fi
done

OS="$(uname -s)"; ARCH="$(uname -m)"
echo "未装,开始安装(OS=$OS ARCH=$ARCH)…"

if command -v brew >/dev/null 2>&1; then
  echo "→ 用 Homebrew 装"
  brew install baidupcs-go
elif [ "$OS" = "Linux" ]; then
  # 服务器无 brew:下 GitHub release(qjfoidnh fork,含分享链接/秒传)
  case "$ARCH" in
    x86_64|amd64) A=amd64 ;;
    aarch64|arm64) A=arm64 ;;
    *) echo "❌ 未知架构 $ARCH,请手动到 https://github.com/qjfoidnh/BaiduPCS-Go/releases 下对应包"; exit 1 ;;
  esac
  TAG="$(curl -fsSL https://api.github.com/repos/qjfoidnh/BaiduPCS-Go/releases/latest | grep -o '"tag_name": *"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
  [ -n "$TAG" ] || { echo "❌ 取不到最新 release tag(网络?)"; exit 1; }
  URL="https://github.com/qjfoidnh/BaiduPCS-Go/releases/download/${TAG}/BaiduPCS-Go-${TAG}-linux-${A}.zip"
  DEST="${GY_NETPAN_BIN_DIR:-$HOME/.local/bin}"; mkdir -p "$DEST"
  TMP="$(mktemp -d)"
  echo "→ 下载 $URL"
  curl -fsSL "$URL" -o "$TMP/pcs.zip"
  unzip -oq "$TMP/pcs.zip" -d "$TMP"
  BINPATH="$(find "$TMP" -type f -name 'BaiduPCS-Go' | head -1)"
  [ -n "$BINPATH" ] || { echo "❌ 解压后没找到 BaiduPCS-Go 可执行"; exit 1; }
  install -m 0755 "$BINPATH" "$DEST/BaiduPCS-Go"
  echo "✅ 装到 $DEST/BaiduPCS-Go(确保 $DEST 在 PATH;或设 GY_NETPAN_BIN=$DEST/BaiduPCS-Go)"
else
  echo "❌ 非 Linux 且无 brew。mac 请先装 Homebrew(https://brew.sh)后重跑。"; exit 1
fi

echo
echo "✅ 安装完成。真跑还需两步(人工):"
echo "   1) 登录(凭证只你输): BaiduPCS-Go login -bduss=<你的BDUSS>"

echo "   登录完成后,agent 就能用 `python3 -m orchestrator material.inbox` 看待入库箱了。"
