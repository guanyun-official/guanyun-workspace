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
    def test_align_pads_missing_tags_no_drop(self):
        # Doubao 返回标签少于图数时,不静默丢图(缺的补 {},后续 _valid_type 兜底)——防 folder2/3 那种静默0
        from scripts.tag_materials import _align
        metas = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        out = _align(metas, [{"类型": "上身图"}])          # 3 张图,Doubao 只返 1 个标签
        self.assertEqual(len(out), 3)                       # 3 张都保留
        self.assertEqual(out[0][1], {"类型": "上身图"})
        self.assertEqual(out[2][1], {})                    # 缺的补空,不丢
        self.assertEqual(_align([], []), [])               # 空不炸

    def test_valid_type_clamps_to_12(self):
        from scripts.tag_materials import _valid_type
        self.assertEqual(_valid_type("面料·纹理特写", "still"), "面料·纹理特写")   # 12类内直取
        self.assertEqual(_valid_type("胡编的类型", "video"), "上身视频")           # 越界→按形态兜底
        self.assertEqual(_valid_type("", "still"), "上身图")                       # 空→兜底

    def test_valid_type_constrains_by_media_kind(self):
        # 视频关键帧(静图)被 Doubao 误标静图类→强制视频类;静图误落视频类→纠回
        from scripts.tag_materials import _valid_type
        self.assertEqual(_valid_type("上身图", "video"), "上身视频")       # 视频不会标成上身图
        self.assertEqual(_valid_type("制作过程视频", "video"), "制作过程视频")  # 视频类保留
        self.assertEqual(_valid_type("上身视频", "still"), "上身图")       # 静图不落视频类

    def test_legacy_rows_selects_empty_relpath_and_old_type(self):
        # 老打标行=相对路径空 且 类型∈旧3类;新行(有相对路径)、人工新建的非旧类型行 都不选(防误删)
        from scripts.tag_materials import _legacy_rows
        mats = [
            {"record_id": "r1", "fields": {"素材编号": "XX-260702-001", "类型": "形象图",
                                           "链接": {"text": "a.jpg"}}},                       # 老行:选中
            {"record_id": "r2", "fields": {"素材编号": "ST-260702-001", "类型": "上身图",
                                           "相对路径": "baidupan:/x/b.jpg", "链接": {"text": "b.jpg"}}},  # 新行:不选
            {"record_id": "r3", "fields": {"素材编号": "ML-1", "类型": "面料·纹理特写",
                                           "链接": {"text": "c.jpg"}}},                        # 人工新建(无relpath但非旧类型):不误删
        ]
        got = _legacy_rows(mats)
        self.assertEqual([g["record_id"] for g in got], ["r1"])
        self.assertEqual(got[0]["file"], "a.jpg")

    def test_reset_legacy_write_backs_up_then_deletes_only_legacy(self):
        # 真删路径 mock 冒烟(gap#4):删前过红线闸+全表备份;只删 legacy 的 record_id;人工非旧类型行不删
        from unittest import mock
        import scripts.tag_materials as t
        import scripts.backup_tables as backup
        from orchestrator import feishu_io, guard
        mats = [
            {"record_id": "r1", "fields": {"素材编号": "XX-1", "类型": "形象图", "链接": {"text": "a.jpg"}}},
            {"record_id": "r2", "fields": {"素材编号": "ST-1", "类型": "上身图",
                                           "相对路径": "baidupan:/x/b.jpg", "链接": {"text": "b.jpg"}}},
            {"record_id": "r3", "fields": {"素材编号": "ML-1", "类型": "面料·纹理特写", "链接": {"text": "c.jpg"}}},
        ]
        deleted, calls = [], []
        with mock.patch.object(feishu_io, "list_records", lambda *a, **k: mats), \
                mock.patch.object(guard, "assert_base_allowed", lambda *a, **k: calls.append("guard")), \
                mock.patch.object(backup, "main", lambda: calls.append("backup")), \
                mock.patch.object(feishu_io, "delete_record", lambda tbl, rid: deleted.append(rid)), \
                mock.patch.object(feishu_io, "log_run", lambda *a, **k: None):
            legacy = t.reset_legacy(write=True)
        self.assertEqual([row["record_id"] for row in legacy], ["r1"])   # 只 r1 是 legacy
        self.assertEqual(deleted, ["r1"])                                # 真删的只有 r1(r3人工行不删)
        self.assertIn("guard", calls)                                    # 删前过 base 红线闸(只测试库)
        self.assertIn("backup", calls)                                   # 删前全表备份(误删可恢复)


if __name__ == "__main__":
    unittest.main()
