"""效果采集 + 反馈(G7)单测。采集默认 stub 零成本;real 走 xhs_fetch(mock,非登录零封号)。"""
import sys
import unittest
from datetime import datetime, timedelta
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

    def test_real_maps_nested_note_interactinfo(self):
        """实测真上线暴露:xhs-extract-master --url 返回的 interactInfo 嵌在 note 下,不是顶层。
        真链 6538dbf7 采到 liked=805/collected=470,零 key(tikhub/redfox 皆✗仍成)。"""
        payload = {"note": {"interactInfo": {"likedCount": "805", "collectedCount": "470",
                                             "commentCount": "92", "shareCount": "104"}}}
        with mock.patch.object(metrics, "_extract_note", return_value=payload):
            got = metrics.collect("https://xiaohongshu.com/note/x", mode="real")
        self.assertEqual(got, {NF.LIKED: 805, NF.COLLECTED: 470, NF.COMMENTS: 92, NF.SHARED: 104})

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

    def test_adds_30_day_and_week_over_week_windows(self):
        now = datetime(2026, 7, 9, 12, 0, 0)

        def ms(days_ago: int) -> int:
            return int((now - timedelta(days=days_ago)).timestamp() * 1000)

        notes = [
            {NF.PLAYBOOK: "考据", NF.LIKED: 300, NF.PUBLISHED_AT: ms(1)},
            {NF.PLAYBOOK: "考据", NF.LIKED: 100, NF.PUBLISHED_AT: ms(8)},
            {NF.PLAYBOOK: "考据", NF.LIKED: 50, NF.PUBLISHED_AT: ms(40)},
            {NF.PLAYBOOK: "ootd", NF.LIKED: 80, NF.PUBLISHED_AT: ms(3)},
        ]

        agg = metrics.aggregate_by_playbook(notes, now=now)

        self.assertEqual(agg["考据"]["近30天"], {"条数": 2, "均赞": 200.0})
        self.assertEqual(agg["考据"]["本周"], {"条数": 1, "均赞": 300.0})
        self.assertEqual(agg["考据"]["上周"], {"条数": 1, "均赞": 100.0})
        self.assertEqual(agg["考据"]["周环比"], 200.0)
        self.assertEqual(agg["ootd"]["上周"], {"条数": 0, "均赞": 0})
        self.assertIsNone(agg["ootd"]["周环比"], "上周均赞为 0 时不伪造环比")


class TestNumRobust(unittest.TestCase):
    """回归锁(实测抓到):飞书数值字段回读常是字符串,聚合取数必须吃字符串/中文计数,否则均赞恒 0。"""

    def test_num_parses_string_and_cn(self):
        self.assertEqual(metrics._num("100"), 100)      # 字符串数字(点赞回读实况)
        self.assertEqual(metrics._num(100), 100)        # int
        self.assertEqual(metrics._num("8.5万"), 85000)  # 中文计数
        self.assertEqual(metrics._num(""), 0)           # 空→0
        self.assertEqual(metrics._num(None), 0)         # None→0

    def test_aggregate_reads_string_liked(self):
        """已发 note 的 点赞='130'(字符串)也能被 aggregate 正确均赞。"""
        notes = [{NF.PLAYBOOK: "素人", NF.LIKED: "130", NF.COLLECTED: "10"},
                 {NF.PLAYBOOK: "素人", NF.LIKED: "160", NF.COLLECTED: "20"}]
        agg = metrics.aggregate_by_playbook(notes)
        self.assertEqual(agg["素人"]["均赞"], 145.0)


if __name__ == "__main__":
    unittest.main()
