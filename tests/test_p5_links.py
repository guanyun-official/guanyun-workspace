"""P5:记录深链与发布包文案红线。零网络。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config
from orchestrator.engine import _package_text


class TestP5(unittest.TestCase):
    def test_record_url_shape(self):
        u = config.record_url("笔记表", "recXXX")
        self.assertIn(config.BASE_TOKEN, u)
        self.assertIn("table=tbl", u)
        self.assertIn("record=recXXX", u)
        self.assertTrue(u.startswith("https://"))

    def test_package_text_has_redline_and_link(self):
        t = _package_text({"文案草稿": "草稿", "排期编号": "PQ-9"}, "PQ-9", "https://x/rec")
        self.assertIn("AI 生成", t)   # 法规红线提示
        self.assertIn("https://x/rec", t)
        self.assertIn("发布链接", t)  # 回填指引

    def test_package_text_lists_linked_materials(self):
        """发布包须列出笔记关联的配套素材——人拿到即知配哪些图/视频,不必回表翻查。"""
        from orchestrator.bitable import NoteFields as NF
        f = {NF.DRAFT: "草稿", NF.CODE: "PQ-9",
             NF.LINKED_MATERIALS: [{"text": "孔府商品图,孔府上身视频",
                                    "text_arr": ["孔府商品图", "孔府上身视频"]}]}
        t = _package_text(f, "PQ-9", "https://x/rec")
        self.assertIn("孔府商品图", t)
        self.assertIn("孔府上身视频", t)
        self.assertIn("配套素材", t)

    def test_package_text_warns_when_no_materials(self):
        """无配套素材须显性警示(防发无图笔记:小红书没图发不出)。"""
        t = _package_text({"文案草稿": "稿", "排期编号": "PQ-0"}, "PQ-0", "https://x/rec")
        self.assertIn("未挂配套素材", t)


class TestHeartbeatDigestDeeplink(unittest.TestCase):
    """巡检提醒消息须带可点击记录深链(确定性,不依赖真实库态/reminders 节流)。

    历史 bug:check_p5 ③ 跑真库 heartbeat 后 grep record=rec,而 shoot/review 受
    reminders「每日最多提醒一次」节流——当天第二次跑就空,验收随即误红。本组测试把
    「巡检消息含深链」这一不变量固化为确定性单测。
    """

    def test_digest_carries_deeplink(self):
        """_digest:shoot/review 条目内嵌的记录深链须原样进入摘要文本。"""
        from datetime import datetime
        from orchestrator.engine import _digest
        url = config.record_url("笔记表", "recDEMO1")
        summary = {"env": "test", "ideas": [], "shoot": [f"款A(拍平铺) {url}"],
                   "review": [], "packages": [], "errors": [], "copy_cost_cny": 0.0}
        out = _digest(summary, datetime(2026, 7, 9, 10, 0))
        self.assertIn("record=recDEMO1", out)  # 可点击深链
        self.assertIn("催拍", out)

    def test_heartbeat_emits_deeplink_reminder(self):
        """端到端:一条待拍素材笔记→REMIND_SHOOT→巡检提醒经 alerts.send 发出且含深链。

        隔离 reminders 节流(临时 STATE_FILE)+ stub 飞书读写 + 捕获 alerts,全确定性。
        """
        import tempfile
        from pathlib import Path
        from unittest import mock
        from orchestrator import alerts, engine, feishu_io, reminders

        notes = [{"record_id": "recT1",
                  "fields": {"状态": "待拍素材", "排期编号": "PQ-T1", "关联衣服": "PQ-T1"}}]
        sent = []

        def fake_list(table):
            return notes if table == "笔记表" else []

        def fake_send(text, *, title="观云推进器"):
            sent.append((title, text))
            return True

        box = Path(tempfile.mkdtemp())
        with mock.patch.object(feishu_io, "list_records", fake_list), \
                mock.patch.object(feishu_io, "update_record", lambda *_a, **_k: None), \
                mock.patch.object(feishu_io, "log_run", lambda *_a, **_k: None), \
                mock.patch.object(engine, "LOCK_FILE", box / "t.lock"), \
                mock.patch.object(reminders, "STATE_FILE", box / "reminder_state.json"), \
                mock.patch.object(alerts, "send", fake_send):
            engine.run(mode="heartbeat", llm_mode="stub")

        joined = "\n".join(t for _, t in sent)
        self.assertIn("record=recT1", joined, f"巡检消息未含记录深链;sent={sent}")
        self.assertTrue(any("巡检" in title for title, _ in sent), f"未触发巡检提醒;sent={sent}")


if __name__ == "__main__":
    unittest.main()
