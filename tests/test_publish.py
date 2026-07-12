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
                {"record_id": "mReal", "fields": {MF.SOURCE: MSrc.REAL, MF.CODE: "M-1", MF.TYPE: "上身视频",
                                                  MF.LINK: {"link": "baidupan:/巧荷素材/03-成片/a.mp4", "text": "a.mp4"}}},
                {"record_id": "mAI", "fields": {MF.SOURCE: MSrc.AI, MF.CODE: "M-2", MF.TYPE: "封面"}},
            ],
        }

    def _run(self, note_fields, write=True):
        updates = []
        base = self._base(note_fields)
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "update_record",
                                  lambda t, r, f: updates.append((r, f))):
            rows = publish.review_approved("巧荷", write=write)
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

    def test_surfaces_material_take_list(self):
        # 答"待发布不知道用哪张":每条带 编号/来源 + 可开链接(网盘指针→用时mint,stub退化为指针)
        note = {NF.STATUS: NS.APPROVED, NF.TITLE: "实拍视频",
                NF.LINKED_MATERIALS: [{"record_ids": ["mReal"]}]}
        rows, _ = self._run(note, write=False)
        mats = rows[0]["materials"]
        self.assertEqual(len(mats), 1)
        self.assertEqual(mats[0]["code"], "M-1")
        self.assertEqual(mats[0]["source"], MSrc.REAL)
        self.assertTrue(mats[0]["取用链接"], "待发布要能看到可开的素材链接")


class TestActionFns(unittest.TestCase):
    """聊天/卡片交互动作函数:approve(人点批准)、fill_publish_link(认领链接,多条命中返候选不瞎写)。"""

    def _patch(self, notes):
        updates = []
        return updates, mock.patch.object(feishu_io, "list_records", lambda t: notes if t == NF.TABLE else []), \
            mock.patch.object(feishu_io, "update_record", lambda t, r, f: updates.append((r, f)))

    def test_approve_only_from_draft_pending(self):
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "稿"}}]
        updates, m1, m2 = self._patch(notes)
        with m1, m2:
            r = publish.approve("n1", write=True)
        self.assertTrue(r["ok"])
        self.assertEqual(updates[0][1][NF.STATUS], NS.APPROVED)

    def test_approve_rejects_wrong_state(self):
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "稿"}}]
        updates, m1, m2 = self._patch(notes)
        with m1, m2:
            r = publish.approve("n1", write=True)
        self.assertFalse(r["ok"])
        self.assertEqual(updates, [])                                   # 不是草稿待发→不动

    def test_fill_link_unique_match_writes(self):
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "浅云", NF.ACCOUNT: "ootd号"}}]
        updates, m1, m2 = self._patch(notes)
        with m1, m2:
            r = publish.fill_publish_link("浅云", "https://xhs/abc", write=True)
        self.assertTrue(r["ok"] and r["matched"] == 1)
        self.assertEqual(updates[0][1][NF.STATUS], NS.PUBLISHED)
        self.assertEqual(updates[0][1][NF.PUBLISH_LINK]["link"], "https://xhs/abc")

    def test_fill_link_ambiguous_returns_candidates(self):
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "OOTD 一", NF.ACCOUNT: "ootd号"}},
                 {"record_id": "n2", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "OOTD 二", NF.ACCOUNT: "ootd号"}}]
        updates, m1, m2 = self._patch(notes)
        with m1, m2:
            r = publish.fill_publish_link("OOTD", "https://xhs/x", write=True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["matched"], 2)
        self.assertEqual(set(r["candidates"]), {"OOTD 一", "OOTD 二"})   # 多条命中→返候选,绝不瞎写
        self.assertEqual(updates, [], "歧义不落库")

    def test_fill_link_skips_already_filled(self):
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.PUBLISHED, NF.TITLE: "已填",
                                                NF.PUBLISH_LINK: {"link": "https://old", "text": "x"}}}]
        _, m1, m2 = self._patch(notes)
        with m1, m2:
            r = publish.fill_publish_link("已填", "https://new", write=True)
        self.assertFalse(r["ok"])                                       # 已有链接的不再认领


if __name__ == "__main__":
    unittest.main()
