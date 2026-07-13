"""规模治理基准:热路径不再全表扫(list_records 计数→0,查询全走服务端过滤 search_records)。
治理前 create_draft_note ~4 次全表拉(账号表×2+素材表+笔记表);治理后全是过滤查询,零全表扫。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import draft, feishu_io  # noqa: E402


class TestScaleBenchmark(unittest.TestCase):
    def test_create_draft_note_zero_full_table_scan(self):
        """★基准★:create_draft_note 的账号/内容类型/素材/笔记查询全走过滤(search_records),零全表拉(list_records)。"""
        r = draft.generate_draft("ootd号", llm_mode="stub")
        fake = {"账号表": [{"record_id": "recACC", "fields": {"账号名": "ootd号"}}],
                "内容类型表": [{"record_id": "recCT", "fields": {"内容类型名": "视频唯美OOTD"}}],
                "素材表": [{"record_id": "recV", "fields": {"类型": "上身视频", "拍摄状态": "已拍"}}]}
        n = {"list": 0, "search": 0}

        def flist(t, **k):
            n["list"] += 1
            return fake.get(t, [])

        def fsearch(t, *a, **k):
            n["search"] += 1
            return fake.get(t, [])

        with mock.patch.object(feishu_io, "list_records", flist), \
                mock.patch.object(feishu_io, "search_records", fsearch), \
                mock.patch.object(feishu_io, "create_record", lambda t, f: "recN"):
            draft.create_draft_note(r)
        self.assertEqual(n["list"], 0, f"create_draft_note 应零全表扫,实际 list_records={n['list']} 次")
        self.assertGreaterEqual(n["search"], 3)   # 账号/内容类型/素材/笔记 走过滤查询(≥3)

    def test_today_panel_zero_full_table_scan(self):
        """today_panel:笔记走过滤(search)、素材按 linked id 取(get_record),**笔记表/素材表零全拉**。
        账号表/内容类型表是小表(name_map 还原 search 的 link 显示名 id→名),有界不累积,允许全拉。"""
        from orchestrator import cockpit, shotlist
        from orchestrator.bitable import NoteFields as NF, NoteStatus as NS, MaterialFields as MF
        from tests._search import search_mock, get_record_mock
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "发",
                  NF.LINKED_MATERIALS: [{"record_ids": ["m1"]}]}}]
        mats = [{"record_id": "m1", "fields": {MF.SOURCE: "实拍", MF.CODE: "M-1", MF.TYPE: "上身图",
                 MF.LINK: {"link": "x", "text": "x"}}}]
        base = {NF.TABLE: notes, MF.TABLE: mats}
        scanned: list[str] = []

        def flist(t, **k):
            scanned.append(t)
            return base.get(t, [])
        with mock.patch.object(feishu_io, "list_records", flist), \
                mock.patch.object(feishu_io, "search_records", search_mock(base)), \
                mock.patch.object(feishu_io, "get_record", get_record_mock(base)), \
                mock.patch.object(shotlist, "shot_needs", lambda b="巧荷": []):
            cockpit.today_panel("巧荷")
        big = [t for t in scanned if t in (NF.TABLE, MF.TABLE)]   # 累积大表
        self.assertEqual(big, [], f"today_panel 不该全表扫累积大表 笔记表/素材表,实际扫了 {big}")

    def test_review_approved_zero_full_table_scan(self):
        """review_approved:已批准笔记走过滤、素材按 linked id 取,零全表拉。"""
        from orchestrator import publish
        from orchestrator.bitable import NoteFields as NF, NoteStatus as NS, MaterialFields as MF
        from tests._search import search_mock, get_record_mock
        notes = [{"record_id": "n1", "fields": {NF.STATUS: NS.APPROVED, NF.TITLE: "稿",
                  NF.LINKED_MATERIALS: [{"record_ids": ["m1"]}]}}]
        mats = [{"record_id": "m1", "fields": {MF.SOURCE: "实拍", MF.CODE: "M-1", MF.TYPE: "上身图"}}]
        base = {NF.TABLE: notes, MF.TABLE: mats}
        n = {"list": 0}

        def flist(t, **k):
            n["list"] += 1
            return base.get(t, [])
        with mock.patch.object(feishu_io, "list_records", flist), \
                mock.patch.object(feishu_io, "search_records", search_mock(base)), \
                mock.patch.object(feishu_io, "get_record", get_record_mock(base)):
            publish.review_approved("巧荷", write=False)
        self.assertEqual(n["list"], 0, f"review_approved 应零全表扫,实际 {n['list']}")

    def test_search_mock_catches_wrong_condition(self):
        """★治假绿自证★:过滤型 search_mock 按条件真过滤——错字段名/错值→0命中,条件拼错会被测出。"""
        from tests._search import search_mock
        from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
        base = {NF.TABLE: [{"record_id": "n1", "fields": {NF.STATUS: NS.APPROVED}}]}
        sm = search_mock(base)
        self.assertEqual(len(sm(NF.TABLE, [{"field_name": NF.STATUS, "operator": "is", "value": [NS.APPROVED]}])), 1)
        self.assertEqual(len(sm(NF.TABLE, [{"field_name": "错字段", "operator": "is", "value": [NS.APPROVED]}])), 0)
        self.assertEqual(len(sm(NF.TABLE, [{"field_name": NF.STATUS, "operator": "is", "value": ["待发布"]}])), 0)


if __name__ == "__main__":
    unittest.main()
