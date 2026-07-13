"""看图打标的多模态 seam(可切换后端)——tagger 只调 `see(images, prompt)` 拿文本,不关心后端。

三层判据里,这是「智能叶子」的入口:看图判断类型/描述是模型的活;这里只做**后端切换 + IO seam**。
- 默认 doubao(ARK/火山,便宜):真跑需 env `ARK_API_KEY`(明文凭证绝不入代码/库;缺 key 报错不静默)。
- 兜底 claude(claude -p,零 key):模型经文件路径看本地图,可切换 seam。
唯一真网络点是 `_post`(urllib,key 留进程内不进 argv);tests mock `_post`/`see` → 零网络。
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from . import config


class VisionError(RuntimeError):
    """看图后端失败(缺 key/网络/返回异常)。message 面向告警可读。"""


def see(image_paths: list[str], prompt: str) -> str:
    """给一批本地图 + 提示词,返回模型文本(打标 JSON 由调用方抽取)。按 config.VISION_BACKEND 选后端。"""
    backend = config.VISION_BACKEND
    if backend == "doubao":
        return _doubao(image_paths, prompt)
    if backend == "claude":
        return _claude(image_paths, prompt)
    raise VisionError(f"未知看图后端 GY_VISION_BACKEND={backend!r}(doubao|claude)")


_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
         ".heic": "image/heic", ".heif": "image/heif"}


def _data_uri(path: str) -> str:
    """本地图 → data URI(ARK 收 image_url,本地图无公网 URL 时用 base64 内联)。
    MIME **按扩展名**定,别一律 jpeg——PNG/WebP 不经转码直达,贴错 MIME 换严格后端会静默解析失败。"""
    mime = _MIME.get(Path(path).suffix.lower(), "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _doubao(image_paths: list[str], prompt: str) -> str:
    """ARK(火山)豆包看图:OpenAI 兼容 chat/completions,content = [image_url...] + text。便宜。"""
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        raise VisionError("doubao 看图需 env ARK_API_KEY(自己终端设置;明文凭证不入代码/库)")
    content: list[dict] = [{"type": "image_url", "image_url": {"url": _data_uri(p)}} for p in image_paths]
    content.append({"type": "text", "text": prompt})
    body = {"model": config.VISION_MODEL, "messages": [{"role": "user", "content": content}]}
    resp = _post(config.ARK_ENDPOINT,
                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise VisionError(f"ARK 返回异常: {str(resp)[:200]}") from e


def _post(url: str, headers: dict, body: dict) -> dict:
    """HTTP POST 的**唯一真网络 seam**(tests mock 此函数)。urllib:key 留进程内不进 argv。"""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:   # noqa: S310 (固定 https 端点)
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001  网络/解析异常统一成 VisionError(面向告警)
        raise VisionError(f"ARK 请求失败: {str(e)[:200]}") from e


def _claude(image_paths: list[str], prompt: str) -> str:
    """claude -p 兜底(零 key):经文件路径看本地图。预算帽由 max-turns 粗控。
    错误语义**与 _doubao 一致**:非零退出/无 JSON/解析失败一律抛 VisionError(不静默吞错→批次静默漏标)。"""
    listing = "\n".join(image_paths)
    full = f"{prompt}\n\n图片(本地路径,逐张看):\n{listing}"
    r = subprocess.run(["claude", "-p", full, "--output-format", "json",
                        "--max-turns", str(4 + 2 * len(image_paths))],
                       capture_output=True, text=True, timeout=600, cwd=str(config.WORKSPACE))
    if r.returncode != 0:
        raise VisionError(f"claude -p 退出非零({r.returncode}): {(r.stderr or r.stdout)[:200]}")
    idx = r.stdout.find("{")
    if idx < 0:
        raise VisionError(f"claude -p 无 JSON 输出: {r.stdout[:200]}")
    try:
        return json.loads(r.stdout[idx:]).get("result", "") or ""
    except (json.JSONDecodeError, ValueError) as e:
        raise VisionError(f"claude -p 输出解析失败: {r.stdout[:200]}") from e
