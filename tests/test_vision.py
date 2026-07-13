"""看图 seam(vision.py):后端切换 + ARK 请求装配 + 返回解析。零网络(mock _post)、零 key 泄漏。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, vision  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
