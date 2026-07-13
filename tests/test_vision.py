"""看图 seam(vision.py):后端切换 + ARK 请求装配 + 返回解析。零网络(mock _post)、零 key 泄漏。"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, vision  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_jpg() -> str:
    d = Path(tempfile.mkdtemp())
    p = d / "a.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")   # 假 jpg 字节:只测 base64 装配,不做真解码
    return str(p)


class TestVision(unittest.TestCase):
    def test_doubao_builds_request_and_parses(self):
        img = _fake_jpg()
        seen = {}

        def fake_post(url, headers, body):
            seen.update(url=url, headers=headers, body=body)
            return {"choices": [{"message": {"content": '[{"类型":"上身图","来源":"实拍"}]'}}]}

        with mock.patch.dict(os.environ, {"ARK_API_KEY": "SECRET"}), \
                mock.patch.object(config, "VISION_BACKEND", "doubao"), \
                mock.patch.object(vision, "_post", fake_post):
            out = vision.see([img], "打标提示词")
        self.assertEqual(out, '[{"类型":"上身图","来源":"实拍"}]')
        # 请求装配:model + content = 图(image_url,base64 内联)+ 文(text)
        self.assertEqual(seen["body"]["model"], config.VISION_MODEL)
        content = seen["body"]["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image_url")
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(content[-1]["type"], "text")
        self.assertIn("Bearer SECRET", seen["headers"]["Authorization"])   # key 从 env 进 header,不进 argv

    def test_doubao_missing_key_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "ARK_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(config, "VISION_BACKEND", "doubao"):
            with self.assertRaises(vision.VisionError):
                vision.see([_fake_jpg()], "x")

    def test_doubao_bad_response_raises(self):
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "K"}), \
                mock.patch.object(config, "VISION_BACKEND", "doubao"), \
                mock.patch.object(vision, "_post", lambda *a: {"unexpected": 1}):
            with self.assertRaises(vision.VisionError):
                vision.see([_fake_jpg()], "x")

    def test_unknown_backend_raises(self):
        with mock.patch.object(config, "VISION_BACKEND", "bogus"):
            with self.assertRaises(vision.VisionError):
                vision.see([], "x")

    def test_data_uri_mime_by_extension(self):
        d = Path(tempfile.mkdtemp())
        png = d / "b.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertTrue(vision._data_uri(str(png)).startswith("data:image/png;base64,"))   # PNG 不再贴 jpeg
        jpg = d / "c.jpg"
        jpg.write_bytes(b"\xff\xd8\xff")
        self.assertTrue(vision._data_uri(str(jpg)).startswith("data:image/jpeg;base64,"))

    def test_claude_backend_parses_result(self):
        out_json = '{"result": "[{\\"类型\\":\\"上身图\\",\\"来源\\":\\"实拍\\"}]"}'
        with mock.patch.object(config, "VISION_BACKEND", "claude"), \
                mock.patch.object(vision.subprocess, "run", lambda *a, **k: _proc(0, out_json)):
            out = vision.see(["/x/a.jpg"], "p")
        self.assertIn("上身图", out)

    def test_claude_nonzero_exit_raises(self):
        # _claude 错误语义与 _doubao 一致:非零退出→VisionError(不静默吞错→批次静默漏标)
        with mock.patch.object(config, "VISION_BACKEND", "claude"), \
                mock.patch.object(vision.subprocess, "run", lambda *a, **k: _proc(1, "", "boom")):
            with self.assertRaises(vision.VisionError):
                vision.see(["/x/a.jpg"], "p")

    def test_claude_no_json_raises(self):
        with mock.patch.object(config, "VISION_BACKEND", "claude"), \
                mock.patch.object(vision.subprocess, "run", lambda *a, **k: _proc(0, "乱码无json")):
            with self.assertRaises(vision.VisionError):
                vision.see(["/x/a.jpg"], "p")


if __name__ == "__main__":
    unittest.main()
