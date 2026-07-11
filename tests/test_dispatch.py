"""轻调度器(#8)派活契约:按 cadence 每号每模式派一条活;一号多模式都覆盖;红线=只派『待出文案』不发布。
纯读声明(离线);写库路径过红线闸(生产库拒)。"""
from __future__ import annotations

import unittest
from unittest import mock

from orchestrator import config, dispatch, feishu_io
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
from orchestrator.guard import GuardError


class DailyAssignments(unittest.TestCase):
    def test_covers_each_account_each_mode(self):
        rows = dispatch.daily_assignments("观云")
        keys = {(r["account"], r["content_type"]) for r in rows}
        self.assertIn(("ootd号", "视频唯美OOTD"), keys)
        self.assertIn(("ootd号", "图文唯美OOTD"), keys)          # 一号多模式:两模式都派
        self.assertIn(("官号@巧荷·东方美学", "品牌新作展示"), keys)
        for r in rows:                                            # 每条活字段齐、sourcing 已知
            self.assertTrue(r["gen_skill"])
            self.assertIn(r["sourcing"], dispatch.SOURCING_HINT)
            self.assertTrue(r["sourcing_hint"])

    def test_trend_imitate_hint_points_to_teardown_skills(self):
        """④ 爆款模仿 sourcing:提示指向已装的爆款拆解技能,不另造。"""
        self.assertIn("爆款雷达", dispatch.SOURCING_HINT["trend_imitate"])
        self.assertIn("explosive-teardown", dispatch.SOURCING_HINT["trend_imitate"])

    def test_dryrun_no_write(self):
        rows = dispatch.dispatch("观云", write=False)
        self.assertEqual(len(rows), len(dispatch.daily_assignments("观云")))


class DispatchRedline(unittest.TestCase):
    def test_write_blocks_prod_base(self):
        """红线:派活写库前过 base 闸,生产库拒(闸先抛,触不到网络)。"""
        o = (config.BASE_TOKEN, config.TEST_MODE)
        try:
            config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
            with self.assertRaises(GuardError):
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
