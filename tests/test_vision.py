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

    def test_data_uri_downscales_large_to_jpeg(self):
        # 大图→降采样到≤1536px再编码jpeg(防专业大图base64过大→ARK Broken pipe)
        import base64 as b64
        import io
        from PIL import Image
        d = Path(tempfile.mkdtemp())
        big = d / "big.png"
        Image.new("RGB", (4000, 3000), (200, 100, 50)).save(big)
        uri = vision._data_uri(str(big))
        self.assertTrue(uri.startswith("data:image/jpeg;base64,"))
        w, h = Image.open(io.BytesIO(b64.b64decode(uri.split(",", 1)[1]))).size
        self.assertLessEqual(max(w, h), 1536)

    def test_data_uri_fallback_on_unopenable(self):
        d = Path(tempfile.mkdtemp())
        bad = d / "bad.png"
        bad.write_bytes(b"not-an-image")                       # PIL 打不开 → 退回原始字节+扩展名MIME
        self.assertTrue(vision._data_uri(str(bad)).startswith("data:image/png;base64,"))

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
