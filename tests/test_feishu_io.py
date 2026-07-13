"""feishu_io.search_records:服务端过滤查询(条件下推 + 分页合并 + 空条件退化 list)。零网络(mock _call)。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, feishu_io  # noqa: E402


class TestSearchRecords(unittest.TestCase):
    def test_pushes_conditions_and_paginates(self):
        pages = [
            {"items": [{"record_id": "r1"}], "has_more": True, "page_token": "t2"},
            {"items": [{"record_id": "r2"}], "has_more": False},
        ]
        calls = []

        def fake_call(method, path, params=None, data=None):
            calls.append((method, path, params, data))
            return pages[len(calls) - 1]

        with mock.patch.object(feishu_io, "_call", fake_call), \
                mock.patch.object(config, "tables", lambda *a, **k: {"素材表": "tblX"}):
            out = feishu_io.search_records("素材表", [{"field_name": "类型", "operator": "is",
                                                      "value": ["上身视频"]}])
        self.assertEqual([r["record_id"] for r in out], ["r1", "r2"])          # 分页合并
        self.assertEqual(calls[0][0], "POST")
        self.assertIn("records/search", calls[0][1])
        self.assertEqual(calls[0][3]["filter"]["conditions"][0]["field_name"], "类型")   # 条件下推进 body
        self.assertEqual(calls[0][3]["filter"]["conjunction"], "and")
        self.assertEqual(calls[1][2]["page_token"], "t2")                      # 第2页带 token

    def test_empty_conditions_falls_back_to_list(self):
        with mock.patch.object(feishu_io, "list_records",
                               lambda t, ps=100: [{"record_id": "all"}]) as _m:
            out = feishu_io.search_records("素材表", [])
        self.assertEqual(out, [{"record_id": "all"}])                          # 空条件→全表(等价 list_records)


if __name__ == "__main__":
    unittest.main()
