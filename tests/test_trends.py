"""找热点→灵感库落库:按标题去重、URL 字段包装、空标题跳过。零网络。"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import trends, feishu_io  # noqa: E402
from orchestrator.bitable import InspirationFields as IF  # noqa: E402


class TestHarvest(unittest.TestCase):
    def _run(self, items, write=True):
        existing = [{"record_id": "i1", "fields": {IF.TITLE: "已有灵感"}}]
        created = []
        with mock.patch.object(feishu_io, "list_records", lambda t: existing), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda t, f: created.append(f) or "recN"):
            res = trends.harvest_trends(items, write=write)
        return res, created

    def test_dedup_wrap_and_skip_empty(self):
        items = [{"标题": "新热点A", "可借鉴": "通勤场景", "源链接": "https://xhs/1"},
                 {"标题": "已有灵感"},          # 去重
                 {"标题": ""}]                   # 空跳过
        res, created = self._run(items)
        self.assertEqual(res["新增"], ["新热点A"])
        self.assertIn("已有灵感", res["去重跳过"])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][IF.TITLE], "新热点A")
        self.assertEqual(created[0][IF.MERITS], "通勤场景")
        self.assertIsInstance(created[0][IF.LINK], dict)         # URL 字段包成 {link,text}
        self.assertEqual(created[0][IF.LINK]["link"], "https://xhs/1")

    def test_dryrun_no_write(self):
        res, created = self._run([{"标题": "新热点B"}], write=False)
        self.assertEqual(res["新增"], ["新热点B"])
        self.assertEqual(created, [], "干跑不写库")


if __name__ == "__main__":
    unittest.main()
