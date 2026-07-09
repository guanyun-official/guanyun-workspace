"""效果采集 + 反馈(G7)单测。采集默认 stub 零成本;real 走 xhs_fetch(mock,非登录零封号)。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import metrics  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402


class TestCollect(unittest.TestCase):
    def test_stub_zero_cost(self):
        self.assertEqual(metrics.collect("https://xiaohongshu.com/note/x", mode="stub"), {},
                         "stub 不触网、返空")

    def test_no_url_returns_empty(self):
        self.assertEqual(metrics.collect("", mode="real"), {})

    def test_real_maps_interactinfo_with_cn_numbers(self):
        # xhs-extract-master note 原子返回 interactInfo,计数可为中文('8.5万')
        payload = {"interactInfo": {"likedCount": "8.5万", "collectedCount": "5.8万",
                                    "commentCount": 815, "shareCount": 4386}}
        with mock.patch.object(metrics, "_extract_note", return_value=payload):
            got = metrics.collect("https://xiaohongshu.com/note/x", mode="real")
        self.assertEqual(got, {NF.LIKED: 85000, NF.COLLECTED: 58000, NF.COMMENTS: 815, NF.SHARED: 4386})

    def test_real_failure_degrades_not_crash(self):
        with mock.patch.object(metrics, "_extract_note", side_effect=RuntimeError("网络挂")):
            self.assertEqual(metrics.collect("https://x", mode="real"), {}, "取数失败返空不炸")

    def test_cn_num_parsing(self):
        self.assertEqual(metrics._cn_num("8.5万"), 85000)
        self.assertEqual(metrics._cn_num("1.2亿"), 120000000)
        self.assertEqual(metrics._cn_num("815"), 815)
        self.assertEqual(metrics._cn_num(4386), 4386)
        self.assertIsNone(metrics._cn_num("-"))
        self.assertIsNone(metrics._cn_num(""))


class TestAggregateByPlaybook(unittest.TestCase):
    def test_aggregates_and_averages(self):
        notes = [
            {NF.PLAYBOOK: "考据", NF.LIKED: 100, NF.COLLECTED: 20, NF.COMMENTS: 3},
            {NF.PLAYBOOK: "考据", NF.LIKED: 200, NF.COLLECTED: 40, NF.COMMENTS: 7},
            {NF.PLAYBOOK: "ootd", NF.LIKED: 50, NF.COLLECTED: 5, NF.COMMENTS: 1},
            {NF.LIKED: 9},  # 无 playbook → 跳过
        ]
        agg = metrics.aggregate_by_playbook(notes)
        self.assertEqual(agg["考据"]["条数"], 2)
        self.assertEqual(agg["考据"]["总赞"], 300)
        self.assertEqual(agg["考据"]["均赞"], 150.0, "反馈信号:考据均赞 150")
        self.assertEqual(agg["ootd"]["总藏"], 5)
        self.assertNotIn("", agg, "无 playbook 的笔记不进聚合")


if __name__ == "__main__":
    unittest.main()
