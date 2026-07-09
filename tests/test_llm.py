"""生成层单测(G10:方法论 playbook 驱动生成)。stub 模式零成本零网络,验证 playbook 被解析并注入。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import accounts, llm  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402


class TestPlaybookRecipe(unittest.TestCase):
    def test_recipe_assembles_declared_fields(self):
        pb = {"id": "考据", "focus": "文物对照", "title_formula": "孤品钩子", "body_formula": "考据升华"}
        r = llm._playbook_recipe(pb)
        self.assertIn("切面=文物对照", r)
        self.assertIn("标题公式=孤品钩子", r)
        self.assertIn("正文公式=考据升华", r)

    def test_recipe_empty_when_none(self):
        self.assertEqual(llm._playbook_recipe(None), "")


class TestGenCopyStubUsesPlaybook(unittest.TestCase):
    def test_stub_reflects_resolved_playbook(self):
        acc = accounts.Account(
            "科普号",
            {"playbooks": [{"id": "考据", "content_type": "文物对照", "weight": 1.0, "view": "考据"}]},
            "画像文本")
        note = {NF.TITLE: "某笔记", NF.CONTENT_TYPE: "文物对照", NF.ACCOUNT: "科普号"}
        with mock.patch.object(accounts, "load", return_value=acc):
            text, cost = llm.gen_copy(note, mode="stub")
        self.assertIn("方法论:考据", text, "stub 应反映解析出的 playbook")
        self.assertEqual(cost, 0.0)

    def test_stub_no_playbook_tag_when_account_unknown(self):
        with mock.patch.object(accounts, "load", return_value=None):
            text, _ = llm.gen_copy({NF.CONTENT_TYPE: "x", NF.ACCOUNT: "无此号"}, mode="stub")
        self.assertNotIn("方法论:", text, "账号解析不到→不该硬凑方法论")


if __name__ == "__main__":
    unittest.main()
