"""回填素材缩略图(base 驾驶舱瞄一眼选材):素材表每条无缩略图的 → 按相对路径拉图 → 生成小缩略图
→ 上传飞书 → 写回『缩略图』附件字段。护本机:低并发 + 每条隔离(坏的跳过) + 每批清缓存。
视频用中点单帧当缩略图。

  python3 -m scripts.backfill_thumbnails --limit 1        # 试跑1条(不写)
  python3 -m scripts.backfill_thumbnails --limit 1 --write  # 真回填1条(验证链路)
  python3 -m scripts.backfill_thumbnails --write            # 全部回填
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable, feishu_io, media, netpan  # noqa: E402
from orchestrator.bitable import MaterialFields as MF  # noqa: E402


def _thumb_token(rel_path: str) -> str:
    """相对路径指针 → 拉图 → 生成缩略图 → 上传 → file_token。视频抽中点单帧。失败抛异常(调用方隔离)。"""
    remote = netpan.pointer_path(rel_path) if rel_path.startswith(netpan.POINTER_SCHEME) else rel_path
    local = netpan.pull(remote, netpan.CACHE)
    kind = media.kind(local)
    if kind == "video":
        view = media.video_keyframe(local, str(netpan.CACHE), n=1)
    elif media.needs_jpg(local):
        view = media.to_jpg(local, str(netpan.CACHE))
    else:
        view = local
    if not Path(view).exists():
        raise RuntimeError("视图缺失(转码/抽帧失败)")
    thumb = str(netpan.CACHE / (Path(view).stem + "_thumb.jpg"))
    media.thumbnail(view, thumb, 400)
    return feishu_io.upload_media(thumb, Path(remote).name + ".jpg")


def _one(row: dict, write: bool) -> bool:
    """回填一条(隔离:坏的跳过打印,不拖垮整体)。返回是否成功。"""
    code = bitable.text(row["fields"].get(MF.CODE))
    try:
        tok = _thumb_token(bitable.text(row["fields"].get(MF.REL_PATH)).strip())
        if write and tok:
            feishu_io.update_record(MF.TABLE, row["record_id"], {MF.THUMB: [{"file_token": tok}]})
        print(f"  {'✓回填' if write else '·试跑'} {code}")
        return bool(tok)
    except Exception as e:  # noqa: BLE001  单条隔离
        print(f"  ⚠跳过 {code}: {str(e)[:60]}", file=sys.stderr)
        return False


def run(limit: int = 0, write: bool = False, concurrency: int = 2) -> int:
    rows = feishu_io.list_records(MF.TABLE)
    todo = [r for r in rows if not r["fields"].get(MF.THUMB)
            and bitable.text(r["fields"].get(MF.REL_PATH)).strip()]
    if limit:
        todo = todo[:limit]
    print(f"待回填缩略图: {len(todo)} 条(并发={concurrency})")
    done = 0
    for i in range(0, len(todo), concurrency):
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            done += sum(ex.map(lambda r: _one(r, write), todo[i:i + concurrency]))
        netpan.clear_cache()
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--concurrency", type=int, default=2)
    a = ap.parse_args()
    if netpan.MODE == "real" and not netpan.logged_in():
        print("❌ 网盘未登录", file=sys.stderr)
        return 2
    n = run(a.limit, a.write, a.concurrency)
    print(f"\n{'✅ 回填' if a.write else '试跑'} {n} 条缩略图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
