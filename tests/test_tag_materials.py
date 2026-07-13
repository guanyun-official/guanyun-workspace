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


class TestTagHelpers(unittest.TestCase):
    def test_valid_type_clamps_to_12(self):
        from scripts.tag_materials import _valid_type
        self.assertEqual(_valid_type("面料·纹理特写", "still"), "面料·纹理特写")   # 12类内直取
        self.assertEqual(_valid_type("胡编的类型", "video"), "上身视频")           # 越界→按形态兜底
        self.assertEqual(_valid_type("", "still"), "上身图")                       # 空→兜底

    def test_legacy_rows_selects_empty_relpath(self):
        # 老打标行(相对路径空)才选中重标;字段归位后入的新行(有相对路径)不动
        from scripts.tag_materials import _legacy_rows
        mats = [
            {"record_id": "r1", "fields": {"素材编号": "XX-260702-001", "类型": "形象图",
                                           "链接": {"text": "a.jpg"}}},
            {"record_id": "r2", "fields": {"素材编号": "ST-260702-001", "类型": "上身图",
                                           "相对路径": "baidupan:/x/b.jpg", "链接": {"text": "b.jpg"}}},
        ]
        got = _legacy_rows(mats)
        self.assertEqual([g["record_id"] for g in got], ["r1"])
        self.assertEqual(got[0]["file"], "a.jpg")


if __name__ == "__main__":
    unittest.main()
