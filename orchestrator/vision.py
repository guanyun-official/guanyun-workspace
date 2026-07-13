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
import time
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
_VISION_MAX_PX = 1536   # 降采样上限:打标不需要全分辨率,大图 base64 过大会让 ARK 连接崩(实测 Broken pipe)


def _data_uri(path: str) -> str:
    """本地图 → data URI(base64 内联)。**先降采样到 _VISION_MAX_PX 再编码 jpeg**——
    专业大图(DSC/PNG 可达一二十MB)base64 过大 → ARK 连接崩(实测 Broken pipe);打标不需要全分辨率,缩了省又稳。
    PIL 打不开(异常格式)→ 退回原始字节 + 扩展名 MIME(不炸)。"""
    try:
        import io

        from PIL import Image
        img = Image.open(path).convert("RGB")
        if max(img.size) > _VISION_MAX_PX:
            img.thumbnail((_VISION_MAX_PX, _VISION_MAX_PX))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001  PIL 打不开→退回原始字节+扩展名MIME(不炸)
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


def _post(url: str, headers: dict, body: dict, retries: int = 3) -> dict:
    """HTTP POST 的**唯一真网络 seam**(tests mock 此函数)。urllib:key 留进程内不进 argv。
    **重试退避**(#41 失败恢复):Broken pipe/Connection reset 等瞬时网络错重试 retries 次,退避 1.5s×次;
    最终仍失败才抛 VisionError(_tag_one_batch 再把该批隔离跳过,不炸整个文件夹)。"""
    payload = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:   # noqa: S310 (固定 https 端点)
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001  瞬时网络错→退避重试;耗尽→VisionError
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise VisionError(f"ARK 请求失败(重试{retries}次): {str(last)[:200]}")


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
