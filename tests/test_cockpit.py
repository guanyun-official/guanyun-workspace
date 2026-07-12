"""今日驾驶舱:笔记按状态分 待审/待发/待回填,聚合要补拍。零网络。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import cockpit, feishu_io, shotlist  # noqa: E402
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS, MaterialFields as MF  # noqa: E402


class TestTodayPanel(unittest.TestCase):
    def _run(self, notes, mats):
        base = {NF.TABLE: notes, MF.TABLE: mats}
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(shotlist, "shot_needs", lambda b="观云": [{"account": "ootd号", "类型": "上身图", "缺": 1, "投递去向": "网盘待入库"}]):
            return cockpit.today_panel("观云")

    def test_buckets_by_status(self):
        notes = [
            {"record_id": "n1", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "待审稿", NF.ACCOUNT: "ootd号"}},
            {"record_id": "n2", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "待发稿", NF.ACCOUNT: "ootd号",
                                           NF.LINKED_MATERIALS: [{"record_ids": ["m1"]}]}},
            {"record_id": "n3", "fields": {NF.STATUS: NS.PUBLISHED, NF.TITLE: "已发没链接", NF.ACCOUNT: "图文号1"}},
            {"record_id": "n4", "fields": {NF.STATUS: NS.PUBLISHED, NF.TITLE: "已发有链接", NF.ACCOUNT: "图文号1",
                                           NF.PUBLISH_LINK: {"link": "https://xhs/x", "text": "x"}}},
        ]
        mats = [{"record_id": "m1", "fields": {MF.SOURCE: "实拍", MF.CODE: "M-1", MF.TYPE: "上身图",
                                               MF.LINK: {"link": "baidupan:/x/a.jpg", "text": "a.jpg"}}}]
        p = self._run(notes, mats)
        self.assertEqual([n["title"] for n in p["待审"]], ["待审稿"])
        self.assertEqual([n["title"] for n in p["待发"]], ["待发稿"])
        self.assertEqual(p["待发"][0]["materials"][0]["code"], "M-1")
        self.assertTrue(p["待发"][0]["materials"][0]["link"])            # 带可开链接
        self.assertEqual([n["title"] for n in p["待回填链接"]], ["已发没链接"])  # 有链接的不进
        self.assertEqual(len(p["要补拍"]), 1)

    def test_empty_day(self):
        p = self._run([], [])
        self.assertEqual(p["待审"], [])
        self.assertEqual(p["待发"], [])
        self.assertEqual(p["待回填链接"], [])


if __name__ == "__main__":
    unittest.main()
