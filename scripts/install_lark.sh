#!/usr/bin/env bash
# 把 hermes 的飞书凭证绑到 lark-cli(幂等)。
#
# 新机器/新 hermes profile 下,直接跑 `lark-cli api ...` 会吐:
#   {"ok":false,"error":{"type":"config","message":"not configured",
#    "hint":"run `lark-cli config init --new` ..."}}
# 数字生命不需要 init(它没有 app secret,那在 ~/.hermes/.env)。
# 正确动作是 **bind** —— 一次性把 hermes 的 FEISHU_APP_ID/SECRET 同步进 lark-cli。
# 已绑时再跑是 no-op(打印"已绑定"),所以装在任何地方都安全。
#
# 这是 harness 的「手」接上来必需的一步,跟 install_sysdeps.sh 同级。
# orchestrator 所有飞书 IO 都走 lark-cli(orchestrator/feishu_io.py),
# 没这步 → board/notes/materials 全部哑火。
set -euo pipefail

if ! command -v lark-cli >/dev/null 2>&1; then
  echo "❌ 找不到 lark-cli。先装 hermes(它自带 lark-cli)。"
  exit 1
fi

if [ ! -f "$HOME/.hermes/.env" ]; then
  echo "❌ ~/.hermes/.env 不存在。hermes 没初始化过 FEISHU_APP_ID/SECRET,没法绑。"
  exit 1
fi

# --source hermes 会自己去读 ~/.hermes/.env 的 FEISHU_APP_ID/SECRET。
# identity 默认 bot-only(= 不允许 user 身份调用),正合我们「一律 --as bot」的纪律。
if out=$(lark-cli config bind --source hermes 2>&1); then
  echo "$out"
else
  echo "❌ bind 失败:"
  echo "$out"
  exit 1
fi

# 自证:用绑好的 bot 身份真打一发 API(列个表),不是只看 bind 命令的退出码。
echo "→ 自证:以 bot 身份列测试库的表名…"
token=$(grep -E '^LARK_APP_TOKEN=' "$(dirname "$0")/../.env" 2>/dev/null | cut -d= -f2- || true)
if [ -z "$token" ]; then
  echo "ℹ️  workspace .env 里没有 LARK_APP_TOKEN,跳过自证(手工跑 board 验)。"
  exit 0
fi
LARK_CLI_NO_PROXY=1 lark-cli api GET "/open-apis/bitable/v1/apps/${token}/tables" \
  --as bot --params '{"page_size":1}' >/tmp/lark_probe_$$.json 2>&1 || {
    echo "❌ 自证失败。bind 可能成功但 API 打不通(权限/网络):"; cat /tmp/lark_probe_$$.json; rm -f /tmp/lark_probe_$$.json; exit 1; }
count=$(python3 -c "import json,sys;d=json.load(open('/tmp/lark_probe_$$.json'));print(len(d.get('data',{}).get('items',[])))" 2>/dev/null || echo 0)
rm -f /tmp/lark_probe_$$.json
echo "✅ lark-cli 已可用(bot 身份,读得到 Base,items=${count})。"
