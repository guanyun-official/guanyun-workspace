"""素材机械拆解:形态判断 + livp(zip)取静帧 + 转码 seam。零网络、转码 mock 不真跑 sips。"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import media  # noqa: E402


class TestKind(unittest.TestCase):
    def test_kind_classification(self):
        self.assertEqual(media.kind("/x/a.mov"), "video")
        self.assertEqual(media.kind("/x/a.MP4"), "video")       # 大小写不敏感
        self.assertEqual(media.kind("/x/a.heic"), "still")
        self.assertEqual(media.kind("/x/a.livp"), "still")
        self.assertEqual(media.kind("/x/note.txt"), "other")

    def test_needs_jpg(self):
        self.assertTrue(media.needs_jpg("/x/a.livp"))
        self.assertTrue(media.needs_jpg("/x/a.HEIC"))
        self.assertFalse(media.needs_jpg("/x/a.jpg"))
        self.assertFalse(media.needs_jpg("/x/a.mov"))


class TestToJpg(unittest.TestCase):
    def test_jpg_passthrough(self):
        # 已是 jpg/png 不转、不调 sips
        with mock.patch.object(media, "_run_convert") as rc:
            self.assertEqual(media.to_jpg("/x/a.jpg"), "/x/a.jpg")
            rc.assert_not_called()

    def test_heic_calls_convert(self):
        with mock.patch.object(media, "_run_convert") as rc:
            out = media.to_jpg("/x/img.heic", out_dir="/tmp/od")
            self.assertEqual(out, "/tmp/od/img.jpg")
            rc.assert_called_once()

    def test_livp_extracts_still_then_converts(self):
        d = Path(tempfile.mkdtemp())
        livp = d / "live.livp"
        with zipfile.ZipFile(livp, "w") as z:      # 造一个 livp(zip 内含 heic + mov)
            z.writestr("live.heic", b"heicbytes")
            z.writestr("live.mov", b"movbytes")
        with mock.patch.object(media, "_run_convert") as rc:
            out = media.to_jpg(str(livp), out_dir=str(d / "out"))
            self.assertTrue(out.endswith("live.jpg"))
            # 转码源是从 livp 里解出的 heic 静帧
            src_arg = rc.call_args[0][0]
            self.assertTrue(src_arg.endswith("live.heic"))

    def test_livp_without_still_raises(self):
        d = Path(tempfile.mkdtemp())
        livp = d / "bad.livp"
        with zipfile.ZipFile(livp, "w") as z:
            z.writestr("bad.mov", b"onlyvideo")
        with self.assertRaises(media.MediaError):
            media.to_jpg(str(livp), out_dir=str(d))


if __name__ == "__main__":
    unittest.main()


class TestVideoKeyframe(unittest.TestCase):
    def test_graceful_on_bad_input(self):
        # 抽不出帧(非视频/不存在)→ 返回原路径,不炸(调用方自行跳过)
        from orchestrator import media
        out = media.video_keyframe("/tmp/__nonexistent__.mp4", "/tmp")
        self.assertEqual(out, "/tmp/__nonexistent__.mp4")


class TestThumbnail(unittest.TestCase):
    def test_thumbnail_downscales_to_max(self):
        from orchestrator import media
        from PIL import Image
        d = Path(tempfile.mkdtemp())
        big = d / "big.jpg"
        Image.new("RGB", (2000, 1500), (100, 150, 200)).save(big)
        out = media.thumbnail(str(big), str(d / "t.jpg"), max_px=400)
        w, h = Image.open(out).size
        self.assertLessEqual(max(w, h), 400)
