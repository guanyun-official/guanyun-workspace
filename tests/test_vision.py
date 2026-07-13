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

    def test_see_with_cost_from_usage(self):
        # 看图成本=实测 usage.total_tokens/1000 × 费率(纳入月度成本硬闸,打标看图不再帽外)
        def fake_post(url, headers, body):
            return {"choices": [{"message": {"content": "[]"}}], "usage": {"total_tokens": 3000}}
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "K"}), \
                mock.patch.object(config, "VISION_BACKEND", "doubao"), \
                mock.patch.object(config, "VISION_COST_PER_1K_CNY", 0.002), \
                mock.patch.object(vision, "_post", fake_post):
            text, cost = vision.see_with_cost([_fake_jpg()], "p")
        self.assertEqual(text, "[]")
        self.assertAlmostEqual(cost, 3000 / 1000 * 0.002)          # 3000 tokens → 0.006 元

    def test_see_with_cost_no_usage_is_zero(self):
        # ARK 没回 usage → 成本 0(未知不假报),不炸
        def fake_post(url, headers, body):
            return {"choices": [{"message": {"content": "[]"}}]}
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "K"}), \
                mock.patch.object(config, "VISION_BACKEND", "doubao"), \
                mock.patch.object(vision, "_post", fake_post):
            _, cost = vision.see_with_cost([_fake_jpg()], "p")
        self.assertEqual(cost, 0.0)

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

    def test_post_retries_then_succeeds(self):
        # #41 失败恢复:瞬时网络错(Broken pipe)退避重试,后续成功不抛
        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": 1}'
        calls = {"n": 0}

        def flaky(req, timeout=120):
            calls["n"] += 1
            if calls["n"] < 2:
                raise OSError("Broken pipe")
            return FakeResp()
        # 网络 seam 已收口到 ark.py(看图/出稿共用一个网络口);vision._post 是转发壳,
        # 保留 VisionError 语义(_tag_one_batch 按它隔离跳批)。所以打 ark.urllib,断言仍在 vision 侧。
        from orchestrator import ark
        with mock.patch.object(ark.urllib.request, "urlopen", flaky), \
                mock.patch.object(ark.time, "sleep", lambda s: None):
            self.assertEqual(vision._post("https://x", {}, {"a": 1}), {"ok": 1})
        self.assertEqual(calls["n"], 2)                     # 第1次失败→重试第2次成功

    def test_post_raises_after_exhausting_retries(self):
        from orchestrator import ark

        def always_fail(req, timeout=120):
            raise OSError("Connection reset by peer")
        with mock.patch.object(ark.urllib.request, "urlopen", always_fail), \
                mock.patch.object(ark.time, "sleep", lambda s: None):
            with self.assertRaises(vision.VisionError):     # ArkError 转成 VisionError,跳批语义不变
                vision._post("https://x", {}, {"a": 1}, retries=2)

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
