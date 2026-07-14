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
    """静图 → jpg 的 subprocess seam(唯一真调用点,可 mock)。**跨平台**(ADR-0009 服务器 7×24):
    mac 用 sips;Linux 用 heif-convert(libheif,heic/heif 专用)或 ImageMagick convert;都没有→报错(装工具)。"""
    import platform
    import shutil
    if platform.system() == "Darwin" and shutil.which("sips"):
        cmd = ["sips", "-s", "format", "jpeg", src, "--out", dst]
    elif src.lower().endswith((".heic", ".heif")) and shutil.which("heif-convert"):
        cmd = ["heif-convert", src, dst]              # libheif,Linux 上 heic/heif 首选
    elif shutil.which("convert"):
        cmd = ["convert", src, dst]                    # ImageMagick(需带 heic delegate)
    elif shutil.which("sips"):
        cmd = ["sips", "-s", "format", "jpeg", src, "--out", dst]
    else:
        raise MediaError("无可用转码工具:mac 需 sips;Linux 需 heif-convert(libheif)或 ImageMagick(convert)")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise MediaError(f"转 jpg 失败({cmd[0]}): {r.stderr[:200]}")


def thumbnail(src: str, dst: str, max_px: int = 400) -> str:
    """生成小缩略图(≤max_px)给 base 驾驶舱瞄一眼选材(不用点开网盘)。返回 dst。PIL 降采样。

    **LOAD_TRUNCATED_IMAGES**(2026-07-14 走摄影师流程真跑发现):真拍的片子入库时报
    `image file is truncated (11 bytes not processed)` → 缩略图生成失败 → **运营在 base 里
    选素材是一片空白**,每张都得点开网盘才知道是什么。而豆包看图明明成功了(标打出来了),
    说明图本身没坏,**是 PIL 的严格模式太苛**:真实相机出的 JPEG 常有轻微截断/EXIF 不规范,
    PIL 默认直接抛错。不放宽的话,真实拍摄的素材会有一大片没有缩略图——直接砸在人面上。
    """
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True     # 真相机出的图常轻微不规范,别为这个丢掉缩略图
    img = Image.open(src)
    img = img.convert("RGB")
    img.thumbnail((max_px, max_px))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=80)
    return dst


def duration(video: str) -> float:
    """视频时长(秒)。**事实**,给 agent 看(25s 的片子和 3 分钟的片子,该抽的帧数不一样)。"""
    return _duration(video)


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


def video_frames(video: str, out_dir: str | None = None, n: int = 5) -> list[dict]:
    """一条视频 → **均匀抽 n 帧,各自一个文件**,返回 [{本地, 秒}]。**给 agent 用自己的眼睛看整条视频。**

    ★为什么不是一帧,也不是拼成一张★

    老实现叫 `video_keyframe`,做两件事,两件都是**替模型做取舍**:
      · **只给一帧**(或"代表帧")—— 而"哪一帧能代表这条视频"**本身就是判断**。
        活证据:库里唯一那条上身视频(EG9A7581.MP4),备注被写成
        「浅粉色…衣身**局部特写**,画面下方有裸露的手臂局部」——
        **一条上身视频,被一帧特写代表了**。补拍单照它去催摄影师"拍个上身视频",
        给的参考却是个局部特写,摄影师当场懵。
      · **把 3 帧横向拼成一张宽图** —— 那是为了迁就"一张图=一个标签"的**批量看图模型**。
        可 agent 是多模态的,**它本来就能分别看每一帧**。拼成一张 = 我提前替它把三帧压成了一个视图,
        它再也看不到"这条视频是怎么走的"。

    现在:**帧分开给,几秒的也标出来**。agent 自己 Read 每一帧,自己综合出"这条视频是什么"。
    看不清?它可以要更多帧(`--frames N`)。**要看多少、看完判成什么,都是它的事。**

    抽不到时长 → 退回 1 秒处一帧(如实标 `秒: null`)。全抽失败 → 空列表(调用方如实报"看不了")。
    """
    od = Path(out_dir) if out_dir else Path(video).parent
    od.mkdir(parents=True, exist_ok=True)
    stem = Path(video).stem
    dur = _duration(video)
    if dur <= 0:                                              # 拿不到时长:抽 1 秒处一帧,如实说不知道在第几秒
        one = od / f"{stem}_f0.jpg"
        return [{"本地": str(one), "秒": None}] if _extract_frame(video, 1.0, one) else []
    out: list[dict] = []
    for i in range(max(1, n)):                                # 均匀取 n 帧(避开首尾极端:i+1 / n+1)
        at = dur * (i + 1) / (n + 1)
        fp = od / f"{stem}_f{i}.jpg"
        if _extract_frame(video, at, fp):
            out.append({"本地": str(fp), "秒": round(at, 1)})
    return out


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
