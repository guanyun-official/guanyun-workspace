"""Bitable 记录适配器(候选A):字段各形态收进窄接口。零网络。"""
import sys, unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable

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

class TestLink(unittest.TestCase):
    """link_record_ids:飞书关联字段回读形态 list[{record_ids:[...]}] → record_id 列表。
    (原经 Record.link_ids 间接测;Record 浅壳已删,自由函数才是唯一收口,直测之。)"""
    def test_shapes(self):
        self.assertEqual(bitable.link_record_ids([{"record_ids":["rec1","rec2"]}]),["rec1","rec2"])
        self.assertEqual(bitable.link_record_ids([{"record_ids":["a"]},{"record_ids":["b"]}]),["a","b"])
        self.assertEqual(bitable.link_record_ids([]),[])         # 空
        self.assertEqual(bitable.link_record_ids(None),[])       # 非 list(未挂关联)
        self.assertEqual(bitable.link_record_ids("rec"),[])      # 标量不误判

if __name__=="__main__": unittest.main()
