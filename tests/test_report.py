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


if __name__ == "__main__":
    unittest.main()
