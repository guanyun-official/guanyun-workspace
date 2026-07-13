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


if __name__ == "__main__":
    unittest.main()
