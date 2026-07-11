#!/usr/bin/env python3
"""视频切片(#2):按镜头(scene detection)把长视频切成细粒度 clip,供细粒度素材归档。

原片不动;ffmpeg 检测 scene change → 按边界切 clip(-c copy 不重编码,快)。切出的 clip 再走 ingest 软链+登记。
  python3 -m scripts.slice_video <video> [--out <dir>] [--threshold 0.3] [--min-len 1.0]
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def _clip_bounds(scene_times: list[float], dur: float, min_len: float = 1.0) -> list[tuple[float, float]]:
    """纯函数(可测):scene change 时间点 + 总时长 → clip 的 (入,出) 边界列表。
    合并太短的段(< min_len)到下一段,避免碎渣;首尾兜 0 和 dur。"""
    pts = sorted({0.0, *[t for t in scene_times if 0 < t < dur], dur})
    out: list[tuple[float, float]] = []
    start = pts[0]
    for t in pts[1:]:
        if t - start >= min_len:
            out.append((round(start, 2), round(t, 2)))
            start = t
    if out and dur - out[-1][1] > 0.01:      # 尾巴并入最后一段
        out[-1] = (out[-1][0], round(dur, 2))
    elif not out:                            # 整条都短于 min_len → 不切,整条一段
        out = [(0.0, round(dur, 2))]
    return out


def detect_scenes(video: Path, threshold: float = 0.3) -> list[float]:
    """ffmpeg scene 检测 → scene change 时间点(秒)。无 ffmpeg/失败 → []。"""
    r = subprocess.run(
        ["ffmpeg", "-i", str(video), "-filter:v", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def _duration(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def slice_video(video: str, out_dir: str, threshold: float = 0.3, min_len: float = 1.0) -> list[str]:
    """把 video 按镜头切成 clip 落 out_dir,返回 clip 路径列表(原片不动,-c copy)。"""
    v = Path(video).expanduser()
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    dur = _duration(v)
    bounds = _clip_bounds(detect_scenes(v, threshold), dur, min_len)
    clips = []
    for i, (s, e) in enumerate(bounds, 1):
        clip = out / f"{v.stem}_clip{i:02d}_{s:.0f}-{e:.0f}s.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(v), "-ss", str(s), "-to", str(e),
                        "-c", "copy", str(clip)], check=True)
        clips.append(str(clip))
    return clips


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--min-len", type=float, default=1.0)
    a = ap.parse_args()
    out = a.out or str(Path(a.video).expanduser().parent / f"{Path(a.video).stem}_clips")
    clips = slice_video(a.video, out, a.threshold, a.min_len)
    print(f"切出 {len(clips)} 个 clip → {out}")
    for c in clips:
        print(f"  {Path(c).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
