"""投递到人眼前(Observation 的最后一公里):文本走 hermes 网关,交互卡片走 lark-cli。

**运营不敲终端。** 算出来、判出来的东西没送到他手机上 = 等于没算。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

HOME_CHAT = os.environ.get("GY_FEISHU_CHAT", "oc_152a1160d240789391546e0a831e9798")


def send_card(card: dict, chat_id: str = "") -> dict:
    """发飞书**交互卡片**(lark-cli raw api, bot 身份)。今日卡片/补拍单/周报卡都走它。

    路径:`POST /open-apis/im/v1/messages?receive_id_type=chat_id` 私聊/群聊通用。
    ⚠️ 老实现走 `lark-cli im +messages-send --chat-id` —— **对 P2P 私聊(oc_)会报
    『out of the chat』**,因为那个子命令要求 bot 是群成员。raw api 没有这个限制。
    (2026-07-15 真验过:发到私聊 oc_152a1160d240789391546e0a831e9798 → code 0。)

    返回 {已发, message_id?, 错?} —— **message_id 就是自证**(拿它去把消息读回来)。

    ★这里出过一次真事故,而且是**反向的谎**★(2026-07-14 数字生命上班第一天抓到)

    老实现判成功是这么写的:

        ok = r.returncode == 0 and '"code":0' in (r.stdout or "")

    **子串匹配一个 JSON。** 而 `lark-cli im +messages-send` 真吐出来的是:

        {"ok": true, "identity": "bot", "data": {"chat_id": ..., "message_id": "om_..."}}

    —— **根本没有 `code` 这个键**(那是 `lark-cli api` 的形态,两个子命令形态完全不同)。
    于是 `send_card` **永远返回 False,而消息其实真的发出去了**。

    这个函数的 docstring 上一版写着:"发失败**如实返回 False** —— 绝不假装发出去了"。
    它防的是"假装成功",**结果掉进了反方向:假装失败**。
    而假装失败**更毒** —— 它诱导 agent 反复重发。数字生命信了它,重发、又发探针诊断,
    **真人群里落了 4 张卡**(2 张重复补拍单 + 2 张废探针),它自己发现后撤回了。

    ★而我修它的时候,又踩了同一个坑★:我"想当然"地改成判 `code == 0` ——
    **真跑一次才发现 im 子命令根本不返 code**。
    **「别信形态,先真读一遍 API 返回」这条,今天在同一个函数上栽了两次。**

    现在:**走 raw api**,返回形态固定 `{"code":0,"data":{...}}`,真解析 JSON,
    并把 **message_id 交出去当自证的钥匙**。
    """
    receive_id = chat_id or HOME_CHAT
    body = {"receive_id": receive_id, "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False)}
    args = ["lark-cli", "api", "POST", "/open-apis/im/v1/messages",
            "--as", "bot",
            "--params", json.dumps({"receive_id_type": "chat_id"}),
            "--data", json.dumps(body, ensure_ascii=False)]
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    try:
        r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=30)
    except Exception as e:  # noqa: BLE001
        return {"已发": False, "错": f"lark-cli 没跑起来:{e}"}
    out = r.stdout or ""
    i = out.find("{")
    if i < 0:
        return {"已发": False, "错": f"没有 JSON 返回:{(out or r.stderr)[-200:]}"}
    try:
        d = json.loads(out[i:])                       # ★真解析,不子串匹配★
    except json.JSONDecodeError as e:
        return {"已发": False, "错": f"返回不是 JSON({e}):{out[i:i + 200]}"}
    # raw api 固定返回 {"code": 0, "data": {"message_id": "om_...", ...}}
    # (保留双形态判定是为了鲁棒 —— 若以后 lark-cli 改包装,不至于再"假装失败"。)
    ok = d.get("ok") is True or d.get("code") == 0
    if not ok:
        return {"已发": False,
                "错": f"飞书拒了:{str({k: d.get(k) for k in ('ok', 'code', 'msg', 'error')})[:200]}"}
    mid = (d.get("data") or {}).get("message_id", "")
    # **message_id 是自证的钥匙**:拿它就能把刚发的那条读回来。
    # 工具说"发了"不算数 —— **读回来才算**。(今天这个函数正是栽在"信了工具的返回值"上。)
    #
    # ⚠️ 下面这两条命令是**真跑验过的**。我第一版在这里写了 `im +messages-get` /
    # `im +messages-delete` —— **那两个子命令根本不存在**(真名是 `+messages-mget`;撤回得走 raw api)。
    # **在一个刚修完"工具在骗人"的函数里,我又亲手塞了两句骗人的提示。** 别猜命令名,去 `--help` 里看。
    return {"已发": True, "message_id": mid,
            "自证": f"lark-cli api GET /open-apis/im/v1/messages/{mid} --as bot" if mid else "",
            "撤回": f"lark-cli api DELETE /open-apis/im/v1/messages/{mid} --as bot" if mid else ""}


def send(text: str, *, title: str = "巧荷推进器") -> bool:
    msg = f"【{title}】\n{text}"
    if os.environ.get("ALERT_DRY_RUN", "0") == "1" or not shutil.which("hermes"):
        print(f"[alert:dry] {msg}")
        return False
    target = os.environ.get("HERMES_TO", "feishu")
    try:
        subprocess.run(["hermes", "send", "--to", target, msg],
                       capture_output=True, text=True, timeout=20, check=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[alert 降级 stdout] {e}\n{msg}")
        return False
