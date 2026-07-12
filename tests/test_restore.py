"""备份 restore 工具契约:link 字段按备份里的名字在当前 base 重解析成新 record_id(旧 id 失效);
scalar 原样;解析不到的 link 丢弃。补齐"误删可恢复"的 restore 半边。"""
from __future__ import annotations

import unittest
from unittest import mock

from orchestrator import feishu_io
import scripts.restore_tables as rt


class RestoreFields(unittest.TestCase):
    def test_reresolves_link_by_name_not_stale_id(self):
        tbl_by_id = {"tblACC": "账号表"}
        backup = {"内容类型名": "素人图文种草", "格式": "图文",
                  "所属账号": [{"record_ids": ["recOLD"], "text_arr": ["图文号1"], "table_id": "tblACC"}]}
        accts = [{"record_id": "recNEW", "fields": {"账号名": "图文号1"}}]
        with mock.patch.object(feishu_io, "list_records", lambda t: accts):
            out = rt.restore_fields(backup, tbl_by_id)
        self.assertEqual(out["内容类型名"], "素人图文种草")   # scalar 原样
        self.assertEqual(out["格式"], "图文")
        self.assertEqual(out["所属账号"], ["recNEW"])          # 按名重解析成新 id,非旧 recOLD

    def test_unresolvable_link_dropped(self):
        tbl_by_id = {"tblACC": "账号表"}
        backup = {"标题": "x", "账号": [{"record_ids": ["recOLD"], "text_arr": ["不存在的号"], "table_id": "tblACC"}]}
        with mock.patch.object(feishu_io, "list_records", lambda t: []):
            out = rt.restore_fields(backup, tbl_by_id)
        self.assertEqual(out["标题"], "x")
        self.assertNotIn("账号", out)                          # 解析不到→丢弃,不写孤儿 id

    def test_url_and_scalar_kept_asis(self):
        out = rt.restore_fields({"发布链接": {"link": "https://x", "text": "https://x"}, "点赞": 100}, {})
        self.assertEqual(out["发布链接"], {"link": "https://x", "text": "https://x"})  # url dict 原样
        self.assertEqual(out["点赞"], 100)


if __name__ == "__main__":
    unittest.main()
