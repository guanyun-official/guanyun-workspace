"""AI声明按素材来源自动判定 + 发布就绪。落地用户规则:实拍免勾、AI合成强制勾。零网络。
红线锁:绝不自动发布(只到待发布)、绝不代勾 AI声明(实拍免除、含AI要求人勾)。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import guard, publish, feishu_io  # noqa: E402
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS, MaterialFields as MF  # noqa: E402
from orchestrator.bitable import MaterialSource as MSrc  # noqa: E402


class TestAiRule(unittest.TestCase):
    def test_required_only_when_any_ai_source(self):
        self.assertFalse(guard.ai_declaration_required([]))              # 无素材→不强制
        self.assertFalse(guard.ai_declaration_required([MSrc.REAL, MSrc.REAL]))  # 全实拍→免勾
        self.assertTrue(guard.ai_declaration_required([MSrc.REAL, MSrc.AI]))     # 含AI合成→必须勾

    def test_gate_exempts_real_footage_requires_ai(self):
        # 全实拍:即使没勾也放行(法规无需 AI 标识)
        guard.assert_ai_declared({NF.CODE: "X"}, ai_required=False)
        # 含AI合成没勾:抛
        with self.assertRaises(guard.GuardError):
            guard.assert_ai_declared({NF.CODE: "X", NF.AI_DECLARED: False}, ai_required=True)
        # 含AI合成已勾:放行
        guard.assert_ai_declared({NF.CODE: "X", NF.AI_DECLARED: True}, ai_required=True)


class TestReviewApproved(unittest.TestCase):
    def _base(self, note_fields):
        return {
            NF.TABLE: [{"record_id": "n1", "fields": note_fields}],
            MF.TABLE: [
                {"record_id": "mReal", "fields": {MF.SOURCE: MSrc.REAL}},
                {"record_id": "mAI", "fields": {MF.SOURCE: MSrc.AI}},
            ],
        }

    def _run(self, note_fields, write=True):
        updates = []
        base = self._base(note_fields)
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record",
                                  lambda t, r, f: updates.append((r, f))):
            rows = publish.review_approved("观云", write=write)
        return rows, updates

    def test_real_footage_advances_without_checkbox(self):
        note = {NF.STATUS: NS.APPROVED, NF.TITLE: "实拍视频",
                NF.LINKED_MATERIALS: [{"record_ids": ["mReal"]}]}   # 全实拍
        rows, updates = self._run(note)
        self.assertFalse(rows[0]["ai_required"])
        self.assertTrue(rows[0]["advanced"])
        self.assertEqual(updates[0][1][NF.STATUS], NS.TO_PUBLISH)   # 推进待发布
        self.assertNotIn(NF.AI_DECLARED, updates[0][1])              # 绝不代勾

    def test_ai_material_unchecked_is_held(self):
        note = {NF.STATUS: NS.APPROVED, NF.TITLE: "含AI片段", NF.AI_DECLARED: False,
                NF.LINKED_MATERIALS: [{"record_ids": ["mReal", "mAI"]}]}  # 含AI生成
        rows, updates = self._run(note)
        self.assertTrue(rows[0]["ai_required"])
        self.assertFalse(rows[0]["advanced"])                       # 未勾→不推进
        self.assertIn("需先勾AI声明", rows[0]["verdict"])
        self.assertEqual(updates, [])                               # 留已批准,不动

    def test_ai_material_checked_advances(self):
        note = {NF.STATUS: NS.APPROVED, NF.TITLE: "含AI片段已勾", NF.AI_DECLARED: True,
                NF.LINKED_MATERIALS: [{"record_ids": ["mAI"]}]}
        rows, updates = self._run(note)
        self.assertTrue(rows[0]["ai_required"] and rows[0]["advanced"])
        self.assertEqual(updates[0][1][NF.STATUS], NS.TO_PUBLISH)

    def test_report_only_does_not_write(self):
        note = {NF.STATUS: NS.APPROVED, NF.TITLE: "实拍",
                NF.LINKED_MATERIALS: [{"record_ids": ["mReal"]}]}
        rows, updates = self._run(note, write=False)
        self.assertFalse(rows[0]["advanced"])
        self.assertEqual(updates, [], "只报告不写库")


if __name__ == "__main__":
    unittest.main()
