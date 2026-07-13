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
from pathlib import Path

from . import ark, config


class VisionError(RuntimeError):
    """看图后端失败(缺 key/网络/返回异常)。message 面向告警可读。"""


def see(image_paths: list[str], prompt: str) -> str:
    """给一批本地图 + 提示词,返回模型文本(打标 JSON 由调用方抽取)。按 config.VISION_BACKEND 选后端。"""
    return see_with_cost(image_paths, prompt)[0]


def see_with_cost(image_paths: list[str], prompt: str) -> tuple[str, float]:
    """看图 + 估算成本(元)=实测 usage.total_tokens/1000 × config.VISION_COST_PER_1K_CNY。
    成本进运行日志→纳入月度成本硬闸(打标看图曾在帽外=成本盲区,这里补上)。
    只有 doubao 后端回 usage;claude 兜底或无 usage → 成本 0(未知,不假报)。"""
    backend = config.VISION_BACKEND
    if backend == "doubao":
        text, tokens = _doubao(image_paths, prompt)
    elif backend == "claude":
        text, tokens = _claude(image_paths, prompt), 0
    else:
        raise VisionError(f"未知看图后端 GY_VISION_BACKEND={backend!r}(doubao|claude)")
    return text, round(tokens / 1000 * config.VISION_COST_PER_1K_CNY, 4)


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


def _doubao(image_paths: list[str], prompt: str) -> tuple[str, int]:
    """ARK(火山)豆包看图:OpenAI 兼容 chat/completions,content = [image_url...] + text。便宜。
    返回 (文本, usage.total_tokens);无 usage→0(成本按 0 记,不假报)。"""
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        raise VisionError("doubao 看图需 env ARK_API_KEY(自己终端设置;明文凭证不入代码/库)")
    content: list[dict] = [{"type": "image_url", "image_url": {"url": _data_uri(p)}} for p in image_paths]
    content.append({"type": "text", "text": prompt})
    body = {"model": config.VISION_MODEL, "messages": [{"role": "user", "content": content}]}
    resp = _post(config.ARK_ENDPOINT,
                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
    try:
        text = resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise VisionError(f"ARK 返回异常: {str(resp)[:200]}") from e
    tokens = 0
    if isinstance(resp, dict) and isinstance(resp.get("usage"), dict):
        tokens = int(resp["usage"].get("total_tokens") or 0)   # 真实用量→成本据此估
    return text, tokens


def _post(url: str, headers: dict, body: dict, retries: int = 3) -> dict:
    """HTTP POST → 转发到**全仓唯一真网络 seam** `ark.post`(看图与出稿共用一个网络口,别开第二个)。
    保留本名 + VisionError 语义:tests 仍 mock `vision._post`,`_tag_one_batch` 仍按 VisionError 隔离跳批。
    重试退避在 ark.post 里(#41 失败恢复:瞬时网络错重试 retries 次,退避 1.5s×次)。"""
    try:
        return ark.post(url, headers, body, retries)
    except ark.ArkError as e:
        raise VisionError(str(e)) from e


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
