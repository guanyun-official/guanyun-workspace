"""每周总结:回流效果→按方法论聚合排名+本周最佳+补拍。纯函数直测(喂字面 notes),零网络。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import report  # noqa: E402
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS  # noqa: E402


class TestWeeklySummary(unittest.TestCase):
    NOTES = [
        {NF.STATUS: NS.PUBLISHED, NF.PLAYBOOK: "视频唯美OOTD", NF.TITLE: "栀子", NF.LIKED: 200},
        {NF.STATUS: NS.PUBLISHED, NF.PLAYBOOK: "视频唯美OOTD", NF.TITLE: "月影", NF.LIKED: 100},
        {NF.STATUS: NS.PUBLISHED, NF.PLAYBOOK: "素人图文种草", NF.TITLE: "白月光", NF.LIKED: 20},
        {NF.STATUS: NS.DRAFT_PENDING, NF.PLAYBOOK: "视频唯美OOTD", NF.LIKED: 0},  # 草稿不计
    ]

    def test_aggregates_ranks_and_top(self):
        s = report.weekly_summary(self.NOTES, needs=[{"account": "ootd号", "类型": "上身图", "缺": 2}])
        pbs = [r["playbook"] for r in s["ranked"]]
        self.assertIn("视频唯美OOTD", pbs)
        self.assertEqual(s["ranked"][0]["playbook"], "视频唯美OOTD")   # 均赞150 > 素人20,排第一
        self.assertEqual(s["by_playbook"]["视频唯美OOTD"]["条数"], 2)   # 草稿不稀释
        self.assertEqual(s["top"]["title"], "栀子")                    # 单条最佳=赞200
        self.assertEqual(s["shot_needs"][0]["缺"], 2)

    def test_format_is_human_readable(self):
        s = report.weekly_summary(self.NOTES)
        txt = report.format_weekly(s)
        self.assertIn("本周复盘", txt)
        self.assertIn("视频唯美OOTD", txt)
        self.assertIn("本周最有效", txt)

    def test_empty_no_crash(self):
        s = report.weekly_summary([])
        self.assertEqual(s["ranked"], [])
        self.assertIn("暂无", report.format_weekly(s))

    def test_zero_likes_gives_no_conclusion(self):
        """**零数据不许编结论**(2026-07-14 走运营流程发现)。真跑出的周报写着:
            「👉 本周最有效:『视频唯美OOTD』——可加权/多产这类」
            「🏆 单条最佳:「OOTD｜栀子入素」赞 0」
        ——而它只有 1 条、均赞 0.0。**0 赞的"最有效"、0 赞的"最佳"**。运营看了会说:
        "就一条,还 0 赞,你让我多产?" 系统刚上线时回流还没数据(赞全 0),周报照样瞎推荐,
        运营照做就被误导。宁可说"数据不够",也不能编。"""
        notes = [{"fields": {NF.STATUS: NS.PUBLISHED, NF.PLAYBOOK: "视频唯美OOTD",
                             NF.TITLE: "刚发还没人赞", NF.LIKED: 0}}]
        txt = report.format_weekly(report.weekly_summary([n["fields"] for n in notes]))
        self.assertNotIn("本周最有效", txt, "零赞时不许下「哪类更有效」的结论")
        self.assertNotIn("单条最佳", txt, "0 赞的「最佳」是荒谬的")
        self.assertIn("给不出", txt)          # 诚实说给不出结论
        self.assertIn("回填", txt)            # 并告诉人多半是没回填真链接


if __name__ == "__main__":
    unittest.main()
