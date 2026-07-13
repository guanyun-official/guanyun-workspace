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
                mock.patch.object(shotlist, "shot_needs", lambda b="巧荷": [{"account": "ootd号", "类型": "上身图", "缺": 1, "投递去向": "网盘待入库"}]):
            return cockpit.today_panel("巧荷")

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
        self.assertIn("open", p["待审"][0])                              # 带 base 深链(引导到base操作)
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

    def test_surfaces_ai_declaration_needed(self):
        # M3:含AI合成素材的待审稿 surface『需AI声明』(人审前就看到⚠️;仍人自己勾)
        notes = [
            {"record_id": "n1", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "含AI稿", NF.ACCOUNT: "ootd号",
                                           NF.LINKED_MATERIALS: [{"record_ids": ["mAI"]}]}},
            {"record_id": "n2", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "全实拍稿", NF.ACCOUNT: "ootd号",
                                           NF.LINKED_MATERIALS: [{"record_ids": ["mReal"]}]}},
            {"record_id": "n3", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "混合稿", NF.ACCOUNT: "ootd号",
                                           NF.LINKED_MATERIALS: [{"record_ids": ["mReal", "mAI"]}]}},
        ]
        mats = [
            {"record_id": "mAI", "fields": {MF.SOURCE: "AI生成", MF.CODE: "ML-1", MF.TYPE: "面料·纹理特写",
                                            MF.LINK: {"link": "x", "text": "x"}}},
            {"record_id": "mReal", "fields": {MF.SOURCE: "实拍", MF.CODE: "ST-1", MF.TYPE: "上身图",
                                              MF.LINK: {"link": "y", "text": "y"}}},
        ]
        p = self._run(notes, mats)
        flags = {n["title"]: n["需AI声明"] for n in p["待审"]}
        self.assertTrue(flags["含AI稿"])          # 含AI素材→需声明
        self.assertFalse(flags["全实拍稿"])        # 全实拍→免声明
        self.assertTrue(flags["混合稿"])           # 实拍+AI混挂→只要有一条AI就需声明(不漏标)
        self.assertIn("⚠️AI声明", str(cockpit.today_card("巧荷", panel=p)["elements"]))   # 卡片渲染⚠️


class TestTodayCard(unittest.TestCase):
    def test_card_partitioned_by_account_mode_no_material_detail(self):
        panel = {"待审": [{"title": "浅云", "account": "ootd号", "mode": "图文唯美OOTD", "open": "https://base/x"}],
                 "待发": [{"title": "白露", "account": "ootd号", "mode": "视频唯美OOTD", "open": "https://base/y",
                          "materials": [{"code": "M-1", "link": "baidupan:/a.jpg"}]}],
                 "待回填链接": [], "要补拍": [{"account": "ootd号", "类型": "上身图", "缺": 1}]}
        card = cockpit.today_card("巧荷", panel=panel)
        self.assertIn("今日面板", card["header"]["title"]["content"])
        blob = str(card["elements"])
        self.assertIn("ootd号 · 图文唯美OOTD", blob)                 # 按账号·模式分块
        self.assertIn("ootd号 · 视频唯美OOTD", blob)
        self.assertIn("📋 [浅云](https://base/x)", blob)             # 待审图标+可点标题(深链)
        self.assertIn("📤 [白露](https://base/y)", blob)             # 待发图标+可点标题
        self.assertNotIn("M-1", blob)                               # 素材细节不进卡片(base 里看)
        self.assertIn("待补拍", blob)
        self.assertIn("上身图×1", blob)

    def test_card_empty_sections_no_crash(self):
        panel = {"待审": [], "待发": [], "待回填链接": [], "要补拍": []}
        card = cockpit.today_card("巧荷", panel=panel)
        self.assertTrue(card["elements"])                            # 空也出结构不炸
        self.assertIn("无待办", str(card["elements"]))


class TestWeeklySchedule(unittest.TestCase):
    @staticmethod
    def _ms(y, m, d):
        from datetime import datetime
        return int(datetime(y, m, d, 9, 0).timestamp() * 1000)   # 9:00 本地,回读同一天

    def test_bucket_by_planned_date(self):
        from datetime import date
        today = date(2026, 7, 13)
        notes = [
            {"record_id": "a", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "今天",
                                          NF.ACCOUNT: "ootd号", NF.PLANNED_AT: self._ms(2026, 7, 13)}},
            {"record_id": "b", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.TITLE: "后天",
                                          NF.ACCOUNT: "图文号1", NF.PLANNED_AT: self._ms(2026, 7, 15)}},
            {"record_id": "c", "fields": {NF.STATUS: NS.APPROVED, NF.TITLE: "没排期", NF.ACCOUNT: "ootd号"}},
            {"record_id": "d", "fields": {NF.STATUS: NS.TO_PUBLISH, NF.TITLE: "逾期未发",
                                          NF.ACCOUNT: "ootd号", NF.PLANNED_AT: self._ms(2026, 7, 10)}},
            {"record_id": "e", "fields": {NF.STATUS: NS.PUBLISHED, NF.TITLE: "已发不算",
                                          NF.ACCOUNT: "ootd号", NF.PLANNED_AT: self._ms(2026, 7, 13)}},
        ]
        v = cockpit._bucket_schedule(notes, today, days=7)
        by_date = {d["date"]: [n["title"] for n in d["notes"]] for d in v["days"]}
        self.assertIn("今天", by_date["07-13"])                       # 计划发布日=今天→今天桶
        self.assertIn("后天", by_date["07-15"])                       # +2 天桶
        self.assertEqual([n["title"] for n in v["未排期"]], ["没排期"])  # 无计划发布日=未排期
        self.assertEqual([n["title"] for n in v["逾期"]], ["逾期未发"])  # 过期且未发
        self.assertEqual(len(v["days"]), 7)                           # 未来7天骨架
        allx = [n for d in v["days"] for n in d["notes"]] + v["未排期"] + v["逾期"]
        self.assertNotIn("已发不算", [n["title"] for n in allx])        # 已发不入排期

    def test_card_only_shows_stocked_days(self):
        view = {"days": [
                    {"date": "07-13", "weekday": "一",
                     "notes": [{"title": "甲", "account": "ootd号", "mode": "", "open": "https://b/x"}]},
                    {"date": "07-14", "weekday": "二", "notes": []}],
                "未排期": [{"title": "乙", "account": "图文号1", "mode": "", "open": ""}], "逾期": []}
        blob = str(cockpit.weekly_schedule_card("巧荷", view=view)["elements"])
        self.assertIn("07-13 周一", blob)
        self.assertIn("[甲](https://b/x)", blob)                      # 可点标题
        self.assertNotIn("07-14", blob)                              # 空日不占版面(增量)
        self.assertIn("未排期", blob)


if __name__ == "__main__":
    unittest.main()
