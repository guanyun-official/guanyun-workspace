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

    def test_search_api_shape(self):
        # dogfood 实测:records/search 返回 link 字段是 dict {'link_record_ids':[...]}(无 text!),
        # 与 list_records/get_record 的 [{record_ids,text}] 不同。两形态都必须认,否则 search 读 link 全断。
        self.assertEqual(bitable.link_record_ids({"link_record_ids": ["recA", "recB"]}), ["recA", "recB"])
        self.assertEqual(bitable.link_record_ids({"link_record_ids": []}), [])      # search 空关联
        self.assertEqual(bitable.link_record_ids({"record_ids": ["recC"]}), ["recC"])  # dict 变体也兜


class TestLinkNames(unittest.TestCase):
    """link_names:link 字段→显示名,三形态通吃(search 回 id 靠 name_map 还原,否则回退 text)。
    dogfood 坑锁:search 形态没 name_map 就全空(账号名/去重键崩)。"""
    def test_search_shape_resolved_via_map(self):
        m = {"recA": "ootd号", "recB": "图文号1"}
        self.assertEqual(bitable.link_names({"link_record_ids": ["recA"]}, m), "ootd号")   # search→id→名
        self.assertEqual(bitable.link_names({"link_record_ids": ["recA", "recB"]}, m), "ootd号,图文号1")

    def test_get_shape_falls_back_to_text(self):
        # get_record/list_records 形态自带 text → 无 map 也能显示(回退)
        self.assertEqual(bitable.link_names([{"record_ids": ["recA"], "text": "ootd号"}], {}), "ootd号")

    def test_plain_string_falls_back(self):
        self.assertEqual(bitable.link_names("ootd号", {}), "ootd号")               # 纯文本回退
        self.assertEqual(bitable.link_names({"link_record_ids": ["recX"]}, {}), "")  # search 但 map 缺→空(真实:未解析)

if __name__=="__main__": unittest.main()
