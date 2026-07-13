"""**幂等回归锁**:所有"修复/同步"类写操作,跑两遍必须结果一样。

2026-07-14 真跑 L14 抓到的教训:`restore()` **不幂等** —— 它把备份里每条都无脑 create 一遍,
完全不看库里有没有。关键词库 32 条 → 真删 1 条(31)→ 跑一次 restore → **38 条**(凭空多 7 条重复),
而被误删的那条**始终没回来**。**在还有数据的表上跑一次,整张表就翻倍污染。**
当时 test_restore.py 里有 3 个测试、全绿 —— 但它们**全在测最容易测的纯函数**(字段级 link 解析),
**真正会毁数据的那个行为(会不会重复插)一个字没测**。

所以:**凡是会写库的"修复/同步"操作,必须有幂等锁**。跑第二遍不许再动任何东西。
这个文件就是那道锁;`scripts/alignment_audit.py` 的 ⑩ 会检查每个这类函数是否在此有锁。
"""
from __future__ import annotations

import unittest
from unittest import mock


class StampPublishedAtIsIdempotent(unittest.TestCase):
    """`publish.stamp_published_at`:给"已发但没发布日"的稿补日期(控量红线的命根子)。
    已有日期的**绝不能再动** —— 否则每天 cron 跑一次就把发布日刷成今天,历史全乱。"""

    def _run(self, notes):
        from orchestrator import feishu_io, publish
        updates = []
        with mock.patch.object(feishu_io, "search_in", lambda t, f, v: notes), \
                mock.patch.object(feishu_io, "update_record",
                                  lambda t, rid, f: updates.append((rid, f))):
            publish.stamp_published_at(write=True)
        return updates

    def test_stamps_only_missing_date(self):
        from orchestrator.bitable import NoteFields as NF
        notes = [
            {"record_id": "need", "fields": {NF.TITLE: "已发无日期",
                                             NF.PUBLISH_LINK: {"link": "https://x", "text": "x"}}},
            {"record_id": "done", "fields": {NF.TITLE: "已发有日期", NF.PUBLISHED_AT: 1783000000000,
                                             NF.PUBLISH_LINK: {"link": "https://y", "text": "y"}}},
        ]
        ups = self._run(notes)
        self.assertEqual([r for r, _ in ups], ["need"], "只补缺日期的那条")

    def test_second_run_changes_nothing(self):
        """跑第二遍(都已有日期)→ 一条都不许再写。否则 cron 每天把发布日刷成今天,历史全乱。"""
        from orchestrator.bitable import NoteFields as NF
        notes = [{"record_id": "done", "fields": {NF.TITLE: "已补过", NF.PUBLISHED_AT: 1783000000000,
                                                  NF.PUBLISH_LINK: {"link": "https://y", "text": "y"}}}]
        self.assertEqual(self._run(notes), [], "已有发布日的,第二遍一条都不许动")

    def test_no_link_not_stamped(self):
        """连链接都没有 → 不是'刚发完',别瞎补日期(补了控量就把没发的算成发了)。"""
        from orchestrator.bitable import NoteFields as NF
        notes = [{"record_id": "nolink", "fields": {NF.TITLE: "已发但没链接"}}]
        self.assertEqual(self._run(notes), [])


class HarvestTrendsIsIdempotent(unittest.TestCase):
    """`trends.harvest_trends`:落灵感库。同一批热点投两遍,第二遍必须全被去重。"""

    def _run(self, items, existing):
        from orchestrator import feishu_io, trends
        from orchestrator.bitable import InspirationFields as IF
        created = []
        rows = [{"record_id": f"r{i}", "fields": {IF.TITLE: t}} for i, t in enumerate(existing)]
        with mock.patch.object(feishu_io, "list_records", lambda t: rows), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda t, f: created.append(f) or "recNEW"):
            res = trends.harvest_trends(items, write=True)
        return res, created

    def test_same_batch_twice_second_is_all_deduped(self):
        items = [{"标题": "爆款A", "文案": "原帖正文A"}, {"标题": "爆款B", "文案": "原帖正文B"}]
        res1, made1 = self._run(items, existing=[])
        self.assertEqual(len(made1), 2)
        res2, made2 = self._run(items, existing=["爆款A", "爆款B"])   # 第二遍:库里已有
        self.assertEqual(made2, [], "同一批投第二遍,一条都不许再落")
        self.assertEqual(len(res2["去重跳过"]), 2)


class MarkIdeaConvertedIsIdempotent(unittest.TestCase):
    """`dispatch.mark_idea_converted`:灵感转化回填(闭合爆款模仿环)。
    重复调用 = 覆盖同一个 link 值,不产生新记录。"""

    def test_writes_link_list_not_string(self):
        """『转化为笔记』是 link 字段:写 record_id **列表**,写字符串会炸(真跑踩过)。"""
        from orchestrator import dispatch, feishu_io
        from orchestrator.bitable import InspirationFields as IF
        ups = []
        with mock.patch.object(feishu_io, "update_record", lambda t, rid, f: ups.append(f)):
            dispatch.mark_idea_converted("recIdea", "recNote")
            dispatch.mark_idea_converted("recIdea", "recNote")     # 再来一遍
        self.assertEqual(ups, [{IF.CONVERTED: ["recNote"]}] * 2, "幂等:两次写的是同一个值")
        self.assertIsInstance(ups[0][IF.CONVERTED], list, "link 字段必须写列表,不是字符串")


if __name__ == "__main__":
    unittest.main()
