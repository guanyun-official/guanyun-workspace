"""素材机械拆解(转码/形态判断):把入库素材归一成可选用形态。纯判断(kind/needs_jpg)可测,转码走 subprocess seam。

ADR-0004 §4:**视频不自动切成文件**(段指针优先,用时再选段)——机械拆解只做两件事:
1. 形态判断(图/视频),给登记时的『类型』和后续打标当线索;
2. livp/heic 静图转 jpg(通用可选用/预览)——手机拍的 livp(=Apple Live Photo,zip 内含 heic+mov)最常见。
真加工出成片(拼接/合成)是**另一步**(剪辑技能→回传 03-成片),不在机械拆解里。
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

STILL_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".livp", ".webp"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
NEED_JPG = {".heic", ".heif", ".livp"}   # 选用/预览前需转成通用 jpg(livp/heic 很多端打不开)
_JPG_OK = {".jpg", ".jpeg", ".png"}


class MediaError(RuntimeError):
    """转码失败/无静帧。message 面向告警可读。"""


def kind(path: str) -> str:
    """素材形态:still(图)/ video(视频)/ other。按扩展名,不读内容(交打标 agent 多模态判内容)。"""
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in STILL_EXT:
        return "still"
    return "other"


def needs_jpg(path: str) -> bool:
    """是否需转 jpg(heic/heif/livp 这类通用性差的静图)。"""
    return Path(path).suffix.lower() in NEED_JPG


def _extract_livp_still(livp: str, out_dir: Path) -> str:
    """livp(=zip,内含 heic/jpg 静帧 + mov 动态)→ 取静帧路径([[xhs-extract-note-id-gotcha]] 无关;livp=zip 是实测坑)。"""
    with zipfile.ZipFile(livp) as z:
        stills = [n for n in z.namelist() if Path(n).suffix.lower() in (STILL_EXT - {".livp"})]
        if not stills:
            raise MediaError(f"livp 内无静帧: {livp}")
        z.extract(stills[0], out_dir)
        return str(out_dir / stills[0])


def _run_convert(src: str, dst: str) -> None:
    """静图 → jpg 的 subprocess seam(唯一真调用点,可 mock;mac 用 sips,Linux 真跑可换 heif-convert/ImageMagick)。"""
    r = subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", dst],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise MediaError(f"sips 转 jpg 失败: {r.stderr[:200]}")


def to_jpg(path: str, out_dir: str | None = None) -> str:
    """把 heic/heif/livp 静图转 jpg(通用可选用/预览);已是 jpg/png 原样返回。返回 jpg 路径。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _JPG_OK:
        return str(p)
    od = Path(out_dir) if out_dir else p.parent
    od.mkdir(parents=True, exist_ok=True)
    src_img = _extract_livp_still(path, od) if ext == ".livp" else path
    dst = str(od / (p.stem + ".jpg"))
    _run_convert(src_img, dst)
    return dst
