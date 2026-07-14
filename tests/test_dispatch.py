"""轻调度器(#8)派活契约:按 cadence 每号每模式派一条活;一号多模式都覆盖;红线=只派『待出文案』不发布。
纯读声明(离线);写库路径过红线闸(生产库拒)。"""
from __future__ import annotations

import unittest
from unittest import mock

from orchestrator import config, dispatch, feishu_io
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
from orchestrator.guard import GuardError


class DailyAssignments(unittest.TestCase):
    # base 账号表全「跟随workspace」(不暂停)——覆盖测试不依赖真库排产态
    ALL_FOLLOW = [{"record_id": f"r{i}", "fields": {"账号名": n, "自动排产": "跟随workspace"}}
                  for i, n in enumerate(["ootd号", "图文号1", "图文号2", "官号@巧荷·东方美学"])]

    def test_covers_each_account_each_mode(self):
        with mock.patch.object(feishu_io, "list_records", lambda t: self.ALL_FOLLOW):
            rows = dispatch.daily_assignments("巧荷")
        keys = {(r["account"], r["content_type"]) for r in rows}
        self.assertIn(("ootd号", "视频唯美OOTD"), keys)
        self.assertIn(("ootd号", "图文唯美OOTD"), keys)          # 一号多模式:两模式都派
        self.assertIn(("官号@巧荷·东方美学", "品牌新作展示"), keys)   # 未暂停→覆盖
        for r in rows:                                            # 每条活字段齐、sourcing 已知
            self.assertTrue(r["gen_skill"])
            self.assertIn(r["sourcing"], dispatch.SOURCING_HINT)
            self.assertTrue(r["sourcing_hint"])

    def test_paused_account_skipped(self):
        """base「自动排产=暂停」→ 该号停派活(base 是运营开关唯一真相,团队点/dedicated agent 都读得到);
        未暂停的照派。反回归:曾经该列是摆设、dispatch 只看 md cadence。"""
        recs = [{"record_id": "r1", "fields": {"账号名": "官号@巧荷·东方美学", "自动排产": "暂停"}},
                {"record_id": "r2", "fields": {"账号名": "ootd号", "自动排产": "跟随workspace"}}]
        with mock.patch.object(feishu_io, "list_records", lambda t: recs):
            accts = {r["account"] for r in dispatch.daily_assignments("巧荷")}
        self.assertNotIn("官号@巧荷·东方美学", accts)   # 暂停→跳过
        self.assertIn("ootd号", accts)                  # 跟随workspace→照派

    def test_sched_decision_three_states(self):
        """自动排产 3 态各有明确语义(不再是开启≡跟随workspace):暂停=停、开启=强制派覆盖md、跟随=按md。"""
        from orchestrator.bitable import AutoSched
        self.assertFalse(dispatch._should_dispatch(AutoSched.PAUSED, 1))     # 暂停→停(覆盖md)
        self.assertTrue(dispatch._should_dispatch(AutoSched.FORCE_ON, 0))    # 开启→强制派(覆盖md=0)
        self.assertTrue(dispatch._should_dispatch(AutoSched.FOLLOW_WS, 1))   # 跟随+md≥1→派
        self.assertFalse(dispatch._should_dispatch(AutoSched.FOLLOW_WS, 0))  # 跟随+md<1→停
        self.assertTrue(dispatch._should_dispatch("", 1))                     # 空=默认按md

    def test_runway_alert_when_materials_low(self):
        """iter12:runway_alert_days 曾是哑字段(设了没催拍)。素材可用≈0 < 阈值 → 催拍该号。"""
        from unittest import mock
        from orchestrator import feishu_io
        fake = {"账号表": [{"record_id": "recA", "fields": {"账号名": "ootd号"}}], "素材表": []}  # 0可用素材
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: fake.get(t, [])):
            alerts = dispatch.runway_alerts("巧荷")
        self.assertIn("ootd号", {a["account"] for a in alerts})   # 0素材<runway_alert_days→催拍

    def test_trend_imitate_hint_points_to_teardown_skills(self):
        """④ 爆款模仿 sourcing:提示指向已装的爆款拆解技能,不另造。"""
        self.assertIn("爆款雷达", dispatch.SOURCING_HINT["trend_imitate"])
        self.assertIn("explosive-teardown", dispatch.SOURCING_HINT["trend_imitate"])

    def test_dryrun_no_write(self):
        rows = dispatch.dispatch("巧荷", write=False)
        self.assertEqual(len(rows), len(dispatch.daily_assignments("巧荷")))

    def test_pending_ideas_only_unconverted_valid(self):
        """灵感库→出稿前置:只捞『未转化+有效标题』的爆款灵感(trend_imitate 原料)。"""
        rows = [
            {"record_id": "i1", "fields": {"标题": "高定工艺印度丝", "优点": "手部特写好",
                                           "链接": "https://xhs/1", "转化为笔记": ""}},
            {"record_id": "i2", "fields": {"标题": "已转化",                              # 已转化→跳
                                           "转化为笔记": [{"record_ids": ["recNote"], "text": "某笔记"}]}},  # link 真形态
            {"record_id": "i3", "fields": {"标题": "（无标题）"}},                        # 无效→跳
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: rows):
            ideas = dispatch.pending_ideas("巧荷")
        self.assertEqual([i["标题"] for i in ideas], ["高定工艺印度丝"])
        self.assertEqual(ideas[0]["可借鉴"], "手部特写好")

    def test_mark_idea_converted_writes_link_list(self):
        """回填闭环:『转化为笔记』是 link 字段,必须写 record_id 列表(实测真跑坑)。"""
        cap = {}
        with mock.patch.object(feishu_io, "update_record",
                               lambda table, rid, f: cap.update(table=table, rid=rid, fields=f)):
            dispatch.mark_idea_converted("recIdea", "recNote")
        self.assertEqual(cap["table"], "灵感库")
        self.assertEqual(cap["fields"]["转化为笔记"], ["recNote"])  # link=列表非字符串


class RunDay(unittest.TestCase):
    """跑一天『中间一条龙』:排期→出文案→挂素材→草稿待发,一条命令产出'今天每号要发什么'。
    人只管头尾:头=拍素材,尾=在 base 审发。红线:止于草稿待发、绝不代勾 AI 声明。"""
    BASE = {
        "账号表": [{"record_id": f"r{i}", "fields": {"账号名": n, "自动排产": "跟随workspace"}}
                  for i, n in enumerate(["ootd号", "图文号1", "图文号2", "官号@巧荷·东方美学"])],
        "内容类型表": [{"record_id": f"c{i}", "fields": {"内容类型名": ct}} for i, ct in enumerate(
            ["视频唯美OOTD", "图文唯美OOTD", "素人图文种草", "品牌新作展示"])],
        "素材表": [], "笔记表": [],
    }

    def test_dry_run_lists_todays_activities_no_write(self):
        created = []
        with mock.patch.object(feishu_io, "list_records", lambda t: self.BASE.get(t, [])), \
                mock.patch.object(feishu_io, "create_record", lambda t, f: created.append(f) or "x"):
            rows = dispatch.run_day("巧荷", write=False)
        self.assertTrue(rows and all(r["status"] == "(干跑)" for r in rows))
        self.assertEqual(created, [], "干跑不写库")

    def test_dry_run_tells_the_truth_about_what_write_would_do(self):
        """**干跑必须和实跑说同一句话**(2026-07-14 以 agent 身份上班,第一件事就撞到)。

        老实现:`def dispatch(...): assigns = daily_assignments(); if not write: return assigns`
        —— 干跑在那一行就返回了,**整段在途去重被跳过**。
        于是干跑打印「今天派活 4 条」,实跑其实**一条都不派**(4 条全在途)。
        干跑存在的**唯一意义**就是"告诉我实跑会发生什么"。它和实跑说的不一样 = 预览就是谎,
        而它是 agent/运营唯一能"先看看"的手段 —— 骗一次,这个手段就废了。
        锁行为:在途的活,**干跑也要标 skipped**。"""
        base = dict(self.BASE)
        base["笔记表"] = [{"record_id": "recX", "fields": {
            NF.STATUS: NS.DRAFT_PENDING, NF.ACCOUNT: [{"record_ids": ["recA"], "text": "ootd号"}],
            NF.CONTENT_TYPE: [{"record_ids": ["recC"], "text": "视频唯美OOTD"}]}}]
        with mock.patch.object(feishu_io, "list_records", lambda t: base.get(t, [])), \
                mock.patch.object(feishu_io, "search_in", lambda t, *a, **k: base.get(t, [])), \
                mock.patch.object(feishu_io, "name_map", lambda t, f: {"recA": "ootd号", "recC": "视频唯美OOTD"}):
            dry = dispatch.dispatch("巧荷", write=False)
        got = {(a["account"], a["content_type"]): a.get("skipped") for a in dry}
        self.assertEqual(got.get(("ootd号", "视频唯美OOTD")), "已在途",
                         "干跑没标 skipped —— 它在告诉人一件实跑不会发生的事")

    def test_write_lands_drafts_for_each_account_mode(self):
        created = []
        # **这条测试原来在偷偷读真库**(2026-07-14 撞到):它 mock 了 list_records,
        # 却**没 mock search_in** —— 而 `_find_inflight_note` / `_open_slots` 走的正是 search_in。
        # 于是这条号称"全离线"的单测每次都真去打飞书,绿不绿取决于**真库当时有没有在途稿**。
        # 那是**假绿**:它证明的不是代码对,而是"今天真库恰好是空的"。
        # (今天真库里躺着 4 条待审稿,新加的防覆盖门一拦,它就红了 —— 红得对。)
        with mock.patch.object(feishu_io, "list_records", lambda t: self.BASE.get(t, [])), \
                mock.patch.object(feishu_io, "search_in", lambda t, *a, **k: self.BASE.get(t, [])), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: self.BASE.get(t, [])), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda t, f: created.append(f) or f"recN{len(created)}"), \
                mock.patch.object(feishu_io, "update_record", lambda t, r, f: None):
            rows = dispatch.run_day("巧荷", llm_mode="stub", write=True)
        landed = [r for r in rows if r.get("status") == NS.DRAFT_PENDING]
        keys = {(r["account"], r["content_type"]) for r in landed}
        self.assertIn(("ootd号", "视频唯美OOTD"), keys)
        self.assertIn(("ootd号", "图文唯美OOTD"), keys)          # 一号多模式两条都出
        self.assertIn(("图文号1", "素人图文种草"), keys)
        self.assertTrue(all(r.get("note_id") and r.get("title") for r in landed))
        for f in created:                                         # 红线:一律草稿待发、绝不代勾 AI 声明
            self.assertEqual(f[NF.STATUS], NS.DRAFT_PENDING)
            self.assertNotIn(NF.AI_DECLARED, f)


class DispatchRedline(unittest.TestCase):
    def test_write_blocks_prod_base(self):
        """红线:派活写库前过 base 闸,生产库拒(闸先抛,触不到网络)。"""
        o = (config.BASE_TOKEN, config.TEST_MODE)
        try:
            config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
            # mock 读(取「自动排产」/去重都不触网)→ 只验写闸:create_record 前抛 GuardError
            with mock.patch.object(feishu_io, "list_records", lambda t: []), \
                    self.assertRaises(GuardError):
                dispatch.dispatch("巧荷", write=True)
        finally:
            config.BASE_TOKEN, config.TEST_MODE = o

    def test_write_creates_need_copy_and_dedups(self):
        """--write 落成『待出文案』;已在途的号×模式跳过(不重复堆活);绝不置已发/AI声明。"""
        created = []
        # 已在途:ootd号×视频唯美OOTD 已有一条待出文案 → 该活应被跳过
        existing = [{"record_id": "r0", "fields": {NF.STATUS: NS.NEED_COPY,
                     NF.ACCOUNT: "ootd号", NF.CONTENT_TYPE: "视频唯美OOTD"}}]
        with mock.patch.object(feishu_io, "list_records", lambda t: existing), \
                mock.patch.object(feishu_io, "search_records", lambda t, *a, **k: existing), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: created.append(fields) or "recNew"):
            rows = dispatch.dispatch("巧荷", write=True)
        skipped = [r for r in rows if r.get("skipped")]
        self.assertTrue(any(r["account"] == "ootd号" and r["content_type"] == "视频唯美OOTD" for r in skipped))
        for f in created:                                        # 派的活一律待出文案,绝不已发/AI声明
            self.assertEqual(f[NF.STATUS], NS.NEED_COPY)
            self.assertNotIn(NF.AI_DECLARED, f)


if __name__ == "__main__":
    unittest.main()
