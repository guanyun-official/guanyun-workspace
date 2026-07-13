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


def thumbnail(src: str, dst: str, max_px: int = 400) -> str:
    """生成小缩略图(≤max_px)给 base 驾驶舱瞄一眼选材(不用点开网盘)。返回 dst。PIL 降采样。"""
    from PIL import Image
    img = Image.open(src).convert("RGB")
    img.thumbnail((max_px, max_px))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=80)
    return dst


def _duration(video: str) -> float:
    """视频时长(秒,ffprobe);拿不到→0。给抽帧定位中点用(避免固定1秒抽到片头黑帧/slate)。"""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", video], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def _extract_frame(video: str, at: float, dst: Path) -> bool:
    """ffmpeg 抽单帧到 dst,成功返 True。"""
    subprocess.run(["ffmpeg", "-y", "-ss", str(max(0.0, at)), "-i", video, "-frames:v", "1", str(dst)],
                   capture_output=True, text=True, timeout=120)
    return dst.exists()


def video_keyframe(video: str, out_dir: str | None = None, n: int = 3) -> str:
    """抽 n 帧(均匀分布,默认首/中/尾)**横向拼成一张**给打标看——单帧可能抽到黑帧/特写不代表整片;
    多帧拼一张=保持"1视图1标签"批模型不破,却让 Doubao 看到整片脉络。返回拼图 jpg 路径。
    n≤1 或拿不到时长→退化单帧(中点/1秒处);全抽失败→返回原视频路径(调用方兜底/跳过)。
    注:视频下载是重活(ADR-0007:baidu 无 range 只能下整包),本函数只管"已在本地的视频"抽帧。"""
    od = Path(out_dir) if out_dir else Path(video).parent
    od.mkdir(parents=True, exist_ok=True)
    stem = Path(video).stem
    dur = _duration(video)
    if n <= 1 or dur <= 0:                                    # 退化单帧(中点,拿不到时长用1秒)
        one = od / f"{stem}_frame.jpg"
        return str(one) if _extract_frame(video, dur * 0.5 if dur > 0 else 1.0, one) else video
    frames = []
    for i in range(n):                                       # 均匀取 n 帧(避开首尾极端)
        fp = od / f"{stem}_f{i}.jpg"
        if _extract_frame(video, dur * (i + 1) / (n + 1), fp):
            frames.append(fp)
    if not frames:
        return video
    if len(frames) == 1:
        return str(frames[0])
    try:                                                    # 横向等高拼接成一张
        from PIL import Image
        imgs = [Image.open(str(f)).convert("RGB") for f in frames]
        h = min(im.height for im in imgs)
        imgs = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in imgs]
        strip = Image.new("RGB", (sum(im.width for im in imgs), h), (255, 255, 255))
        x = 0
        for im in imgs:
            strip.paste(im, (x, 0))
            x += im.width
        out = od / f"{stem}_frames.jpg"
        strip.save(str(out), "JPEG", quality=85)
        return str(out)
    except Exception:  # noqa: BLE001  拼接失败→退回第一帧(仍可打标)
        return str(frames[0])


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
