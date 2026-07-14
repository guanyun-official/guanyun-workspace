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
import urllib.error
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
        except urllib.error.HTTPError as e:
            # **把返回体读出来**(2026-07-14):原来只留 `HTTPError: 404 Not Found` ——
            # 而方舟真正的话是 `{"error":{"code":"ModelNotOpen","message":"…请在控制台开通…"}}`。
            # 报错不带真相 = 等于没报:我当时只看到 404,差点断言成"端点写错了"。
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:300]
            except Exception:  # noqa: BLE001, S110  读不出 body 就算了,不能让诊断路径自己炸
                pass
            last = f"HTTP {e.code}: {detail or e.reason}"
            if e.code in (400, 401, 403, 404):
                break                        # 客户端错(没开通/没权限/模型名错)重试无意义,别白等
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
        except Exception as e:  # noqa: BLE001  瞬时网络错→退避重试;耗尽→抛
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise ArkError(f"ARK 请求失败: {str(last)[:320]}")


class ModelNotOpen(ArkError):
    """模型在方舟存在,但**这个账号没开通**。人去控制台点一下即可——不是代码能修的,别静默降级假装没事。"""


def image(prompt: str, model: str = "", size: str = "2K") -> str:
    """文生图(方舟 images/generations)→ 图片 URL。**加工环生成 AI 封面/AI 画面用的就是它**。

    产出**必然是 AI 生成像素** → 调用方须用 `processing.derive_source(..., used_ai_generation=True)`
    把成片来源定成『AI生成』→ 下游笔记的 **AI 声明门**据此要求人勾声明(合规红线,机器绝不代勾)。

    模型没开通 → 抛 ModelNotOpen(**不静默退回原图**):加工环判定"该加封面"却悄悄没加,
    人会以为封面加上了 —— 那正是"想起来方便的逻辑"。宁可明说"没开通",也不假装做过。
    """
    body = {"model": model or config.IMAGE_MODEL, "prompt": prompt,
            "size": size, "response_format": "url", "watermark": False}
    try:
        resp = post(config.ARK_IMAGE_ENDPOINT,
                    {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
                    body, retries=2)
    except ArkError as e:
        if "ModelNotOpen" in str(e) or "404" in str(e):
            raise ModelNotOpen(
                f"图像模型「{model or config.IMAGE_MODEL}」当前账号未开通 —— "
                f"去火山方舟控制台『开通管理』搜 Seedream 开通即可(一次点击,人做,我不碰账号设置)。"
                f"在此之前:加工环判『该生成 AI 封面』时会**如实报错**,绝不悄悄跳过") from e
        raise
    try:
        return str(resp["data"][0]["url"])
    except (KeyError, IndexError, TypeError) as e:
        raise ArkError(f"ARK 生图返回形态异常: {str(resp)[:200]}") from e
