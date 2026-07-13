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
        with mock.patch.object(feishu_io, "list_records", lambda t: accts), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: accts):
            out = rt.restore_fields(backup, tbl_by_id)
        self.assertEqual(out["内容类型名"], "素人图文种草")   # scalar 原样
        self.assertEqual(out["格式"], "图文")
        self.assertEqual(out["所属账号"], ["recNEW"])          # 按名重解析成新 id,非旧 recOLD

    def test_unresolvable_link_dropped(self):
        tbl_by_id = {"tblACC": "账号表"}
        backup = {"标题": "x", "账号": [{"record_ids": ["recOLD"], "text_arr": ["不存在的号"], "table_id": "tblACC"}]}
        with mock.patch.object(feishu_io, "list_records", lambda t: []), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: []):
            out = rt.restore_fields(backup, tbl_by_id)
        self.assertEqual(out["标题"], "x")
        self.assertNotIn("账号", out)                          # 解析不到→丢弃,不写孤儿 id

    def test_url_and_scalar_kept_asis(self):
        out = rt.restore_fields({"发布链接": {"link": "https://x", "text": "https://x"}, "点赞": 100}, {})
        self.assertEqual(out["发布链接"], {"link": "https://x", "text": "https://x"})  # url dict 原样
        self.assertEqual(out["点赞"], 100)


if __name__ == "__main__":
    unittest.main()


class RestoreOnlyFillsMissing(unittest.TestCase):
    """**回归锁:恢复=只补缺的,不是盲目重灌**(2026-07-14 真跑 L14 才发现的破坏性 bug)。

    真跑:关键词库 32 条 → 真删 1 条(31)→ 跑 restore → **38 条**(凭空多出 7 条重复),
    而被误删的那一条**始终没回来**。**「误删可恢复」是假的** —— 它不是恢复,是复制粘贴,
    而且是**破坏性的**:在还有数据的表上跑一次,整张表就翻倍污染。

    而这个文件里原本的 3 个测试,**全都在测 `restore_fields()`(字段级 link 解析)**——
    最容易测的纯函数测得漂漂亮亮,**真正会毁数据的那个行为(会不会重复插)一个字没测**。
    备份脚本有、恢复脚本有、测试绿、门也绿 —— 而"真删一条再恢复"从来没人真跑过。
    """

    def _restore(self, backup_recs, live_recs):
        from unittest import mock
        import scripts.restore_tables as rt
        from orchestrator import feishu_io
        created = []
        with mock.patch.object(rt, "_table_name_by_id", lambda: {}), \
                mock.patch.object(feishu_io, "list_records", lambda t: live_recs), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda t, f: created.append(f) or "recNEW"), \
                mock.patch("json.loads", lambda s: backup_recs), \
                mock.patch("pathlib.Path.read_text", lambda self, **k: "[]"):
            rt.restore("backups/x", "关键词库", write=True)
        return created

    def test_only_missing_records_are_created(self):
        backup = [{"fields": {"关键词": "新中式"}}, {"fields": {"关键词": "被误删的词"}}]
        live = [{"record_id": "r1", "fields": {"关键词": "新中式"}}]     # 库里已有第一条
        created = self._restore(backup, live)
        self.assertEqual(len(created), 1, "只该补库里缺的那一条")
        self.assertEqual(created[0]["关键词"], "被误删的词")

    def test_idempotent_nothing_missing_creates_nothing(self):
        """跑第二遍不许再插 —— 这是'恢复'和'复制粘贴'的分水岭。"""
        backup = [{"fields": {"关键词": "新中式"}}]
        live = [{"record_id": "r1", "fields": {"关键词": "新中式"}}]
        self.assertEqual(self._restore(backup, live), [], "库里一条不缺时,一条都不许插")

    def test_fingerprint_ignores_link_fields(self):
        """指纹只用标量字段:link 的 record_id 跨 base 会失效,拿它比会把所有记录都当成'缺失'。"""
        from scripts.restore_tables import _fingerprint
        a = {"关键词": "新中式", "灵感库-关联关键词": [{"record_ids": ["recOLD"]}]}
        b = {"关键词": "新中式", "灵感库-关联关键词": [{"record_ids": ["recNEW"]}]}
        self.assertEqual(_fingerprint(a), _fingerprint(b), "link 变了不影响身份,否则会重复插")
