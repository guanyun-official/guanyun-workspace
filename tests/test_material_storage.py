"""素材存储契约:账本(素材表)须能记'媒体的相对路径 + 来源',大文件走盘不进表。

固化决策(AGENTS.md 素材库约定):生成媒体同拍摄媒体走盘(02-AI生成/03-成片),
素材表 `链接`(text) 存相对路径、`来源` 标 AI生成/实拍、`生成参数` 记 prompt。
本测试锁住这个结构前提——若有人删掉'链接'路径载体或改其类型,账本就记不了路径,
半夜引擎取不到成片、发布包也拼不出配套素材。纯读 schema 契约,零网络。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestMaterialStorage(unittest.TestCase):
    def _fields(self) -> dict:
        d = json.loads((ROOT / "schema/test/素材表.json").read_text(encoding="utf-8"))
        return {f["field_name"]: f["type"] for f in d["fields"]}

    def test_has_relative_path_carrier(self):
        """素材表须有 '链接'(text) 字段作相对路径载体(账本记路径的结构前提)。"""
        flds = self._fields()
        self.assertIn("链接", flds, "素材表缺 '链接' 字段——账本无处记媒体相对路径")
        self.assertEqual(flds["链接"], "text", "'链接' 应为 text(存相对路径),不是附件/其它类型")

    def test_can_mark_generated_source(self):
        """素材表须能区分来源(AI生成/实拍)并记生成参数——生成媒体是一等公民。"""
        flds = self._fields()
        self.assertIn("来源", flds, "素材表缺 '来源' 字段——无法区分 AI生成/实拍")
        self.assertIn("生成参数", flds, "素材表缺 '生成参数' 字段——AI 生成媒体无处记 prompt/模型")


if __name__ == "__main__":
    unittest.main()
