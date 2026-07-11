"""视频切片(#2)边界逻辑契约:纯函数 _clip_bounds 可测(不依赖 ffmpeg/视频)。
ffmpeg 切片本身是集成动作,真跑另证(dogfood 真视频)。"""
from __future__ import annotations

import unittest

from scripts.slice_video import _clip_bounds


class ClipBounds(unittest.TestCase):
    def test_merges_short_segments_and_covers_full(self):
        # scene changes 5 / 5.5(太短并入) / 10;总时长 15
        b = _clip_bounds([5.0, 5.5, 10.0], 15.0, min_len=1.0)
        self.assertEqual(b, [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)])
        self.assertEqual(b[0][0], 0.0)          # 首兜 0
        self.assertEqual(b[-1][1], 15.0)        # 尾兜 dur,全覆盖不丢帧

    def test_whole_video_shorter_than_minlen_stays_one(self):
        self.assertEqual(_clip_bounds([], 0.5, min_len=1.0), [(0.0, 0.5)])  # 整条短→不切成一段

    def test_no_scene_change_one_clip(self):
        b = _clip_bounds([], 15.0, min_len=1.0)
        self.assertEqual(b, [(0.0, 15.0)])      # 无镜头切换→整条一段

    def test_out_of_range_scenes_ignored(self):
        b = _clip_bounds([-1.0, 0.0, 20.0, 8.0], 15.0, min_len=1.0)
        self.assertEqual(b, [(0.0, 8.0), (8.0, 15.0)])  # 越界(负/超dur)点被忽略


if __name__ == "__main__":
    unittest.main()
