"""Bitable 记录适配器(候选A):字段各形态收进窄接口。零网络。"""
import sys, unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable
from orchestrator.bitable import Record, NoteFields as NF

MS = lambda d: int(d.timestamp()*1000)

class TestText(unittest.TestCase):
    def test_all_shapes(self):
        self.assertEqual(bitable.text("直"), "直")                       # 标量
        self.assertEqual(bitable.text(None), "")
        self.assertEqual(bitable.text([{"text":"a"},{"text":"b"}]), "a,b") # list[dict]
        self.assertEqual(bitable.text({"text":"x"}), "x")                 # dict
        self.assertEqual(bitable.text({"link":"http://x"}), "http://x")

class TestTs(unittest.TestCase):
    def test_shapes(self):
        ms=MS(datetime(2026,7,8))
        self.assertIsNotNone(bitable.parse_ts(ms))
        self.assertIsNotNone(bitable.parse_ts([{"value":ms}]))
        self.assertIsNotNone(bitable.parse_ts({"value":[ms]}))
        self.assertIsNone(bitable.parse_ts([]))
        self.assertIsNone(bitable.parse_ts(None))

class TestRecord(unittest.TestCase):
    def test_wraps_fields_or_record(self):
        r1=Record({"fields":{"状态":"已发"},"record_id":"r1"})
        self.assertEqual(r1.text(NF.STATUS),"已发"); self.assertEqual(r1.record_id,"r1")
        r2=Record({"状态":"待发布"})                       # 直接给 fields
        self.assertEqual(r2.text(NF.STATUS),"待发布")
    def test_link_ids_and_bool(self):
        r=Record({"关联衣服":[{"record_ids":["rec1","rec2"]}],"AI声明":True})
        self.assertEqual(r.link_ids(NF.LINKED_CLOTHES),["rec1","rec2"])
        self.assertTrue(r.bool(NF.AI_DECLARED))

if __name__=="__main__": unittest.main()
