"""自动打标:claude 输出 → JSON 数组抽取(容错 ```json 包裹/前后废话)。零网络(不调 claude)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tag_materials import _extract_json  # noqa: E402


class TestExtractJson(unittest.TestCase):
    def test_plain_array(self):
        out = _extract_json('[{"类型":"上身图","来源":"实拍"}]')
        self.assertEqual(out[0]["类型"], "上身图")

    def test_wrapped_and_chatter(self):
        text = '好的,结果如下:\n```json\n[{"类型":"形象图"},{"类型":"上身视频"}]\n```\n以上。'
        out = _extract_json(text)
        self.assertEqual([o["类型"] for o in out], ["形象图", "上身视频"])

    def test_garbage_returns_empty(self):
        self.assertEqual(_extract_json("没有json"), [])
        self.assertEqual(_extract_json("[坏的 json"), [])


if __name__ == "__main__":
    unittest.main()
