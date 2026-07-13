"""ARK(火山方舟/豆包)薄客户端:**全仓唯一真网络 seam**(HTTP POST),看图(vision)与出稿(llm)共用。

为什么存在(dogfood 2026-07-14 真跑实证):出稿原走 `claude -p`,**每次调用吞 ~33K token 的 Claude Code
系统提示/工具定义**(实测:让它只回"测试成本"四个字,cache_creation_input_tokens=32766,花 1.48 元)。
于是一条 200 字小红书文案要 2~3 元——95% 的钱付给了 CLI 的系统提示,与文案长度/模型档次几乎无关。
直连 ARK:prompt 就是 prompt,token 就是 token,同样的稿约 0.0x 元,便宜两个数量级。

凭证只从 env 读(ARK_API_KEY),urllib 走 body 不进 argv(明文凭证绝不入代码/库/进程列表)。
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from . import config


class ArkError(RuntimeError):
    """ARK 调用失败(缺 key / 网络重试耗尽 / 返回形态异常)。不静默吞——吞了就是静默漏标/空稿。"""


def api_key() -> str:
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        raise ArkError("需 env ARK_API_KEY(自己终端设置;明文凭证不入代码/库)")
    return key


def post(url: str, headers: dict, body: dict, retries: int = 3) -> dict:
    """HTTP POST 的**唯一真网络 seam**(tests mock 此函数)。urllib:key 留进程内不进 argv。
    **重试退避**(#41 失败恢复):Broken pipe/Connection reset 等瞬时网络错重试 retries 次,退避 1.5s×次;
    最终仍失败才抛(调用方再决定隔离跳过还是炸)。"""
    payload = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:   # noqa: S310 (固定 https 端点)
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001  瞬时网络错→退避重试;耗尽→抛
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise ArkError(f"ARK 请求失败(重试{retries}次): {str(last)[:200]}")


def chat(prompt: str, model: str = "") -> tuple[str, int]:
    """纯文本 chat(OpenAI 兼容 chat/completions)→ (成稿文本, usage.total_tokens)。
    无 usage → tokens=0(成本按 0 记,**不假报**)。空文本视为失败(空稿比坏稿更坑,别静默落库)。"""
    body = {"model": model or config.DRAFT_MODEL,
            "messages": [{"role": "user", "content": prompt}]}
    resp = post(config.ARK_ENDPOINT,
                {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}, body)
    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise ArkError(f"ARK 返回形态异常: {str(resp)[:200]}") from e
    if not text:
        raise ArkError(f"ARK 空结果: {str(resp)[:200]}")
    tokens = 0
    if isinstance(resp.get("usage"), dict):
        tokens = int(resp["usage"].get("total_tokens") or 0)   # 真实用量→成本据此估,不拍脑袋
    return text, tokens
