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
            rows = dispatch.daily_assignments("观云")
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
            accts = {r["account"] for r in dispatch.daily_assignments("观云")}
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
        with mock.patch.object(feishu_io, "list_records", lambda t: fake.get(t, [])):
            alerts = dispatch.runway_alerts("观云")
        self.assertIn("ootd号", {a["account"] for a in alerts})   # 0素材<runway_alert_days→催拍

    def test_trend_imitate_hint_points_to_teardown_skills(self):
        """④ 爆款模仿 sourcing:提示指向已装的爆款拆解技能,不另造。"""
        self.assertIn("爆款雷达", dispatch.SOURCING_HINT["trend_imitate"])
        self.assertIn("explosive-teardown", dispatch.SOURCING_HINT["trend_imitate"])

    def test_dryrun_no_write(self):
        rows = dispatch.dispatch("观云", write=False)
        self.assertEqual(len(rows), len(dispatch.daily_assignments("观云")))

    def test_pending_ideas_only_unconverted_valid(self):
        """灵感库→出稿前置:只捞『未转化+有效标题』的爆款灵感(trend_imitate 原料)。"""
        rows = [
            {"record_id": "i1", "fields": {"标题": "高定工艺印度丝", "优点": "手部特写好",
                                           "链接": "https://xhs/1", "转化为笔记": ""}},
            {"record_id": "i2", "fields": {"标题": "已转化", "转化为笔记": "recNote"}},  # 已转化→跳
            {"record_id": "i3", "fields": {"标题": "（无标题）"}},                        # 无效→跳
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: rows):
            ideas = dispatch.pending_ideas("观云")
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


class DispatchRedline(unittest.TestCase):
    def test_write_blocks_prod_base(self):
        """红线:派活写库前过 base 闸,生产库拒(闸先抛,触不到网络)。"""
        o = (config.BASE_TOKEN, config.TEST_MODE)
        try:
            config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
            # mock 读(取「自动排产」/去重都不触网)→ 只验写闸:create_record 前抛 GuardError
            with mock.patch.object(feishu_io, "list_records", lambda t: []), \
                    self.assertRaises(GuardError):
                dispatch.dispatch("观云", write=True)
        finally:
            config.BASE_TOKEN, config.TEST_MODE = o

    def test_write_creates_need_copy_and_dedups(self):
        """--write 落成『待出文案』;已在途的号×模式跳过(不重复堆活);绝不置已发/AI声明。"""
        created = []
        # 已在途:ootd号×视频唯美OOTD 已有一条待出文案 → 该活应被跳过
        existing = [{"record_id": "r0", "fields": {NF.STATUS: NS.NEED_COPY,
                     NF.ACCOUNT: "ootd号", NF.CONTENT_TYPE: "视频唯美OOTD"}}]
        with mock.patch.object(feishu_io, "list_records", lambda t: existing), \
                mock.patch.object(feishu_io, "create_record",
                                  lambda table, fields: created.append(fields) or "recNew"):
            rows = dispatch.dispatch("观云", write=True)
        skipped = [r for r in rows if r.get("skipped")]
        self.assertTrue(any(r["account"] == "ootd号" and r["content_type"] == "视频唯美OOTD" for r in skipped))
        for f in created:                                        # 派的活一律待出文案,绝不已发/AI声明
            self.assertEqual(f[NF.STATUS], NS.NEED_COPY)
            self.assertNotIn(NF.AI_DECLARED, f)


if __name__ == "__main__":
    unittest.main()
