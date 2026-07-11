"""回流采集薄执行器(效果闭环第二半)契约:读已发笔记→采集互动数据→写回点赞/收藏。
全离线(mock,零网络零成本):证明管道成形与红线(只写测试库、stub 不造假)。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import collect, config, feishu_io, metrics  # noqa: E402
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS  # noqa: E402
from orchestrator.guard import GuardError  # noqa: E402


class PublishedNotesFilter(unittest.TestCase):
    def test_only_published_with_link(self):
        notes = [
            {"record_id": "rP", "fields": {NF.STATUS: NS.PUBLISHED, NF.PUBLISH_LINK: "http://x"}},
            {"record_id": "rNoLink", "fields": {NF.STATUS: NS.PUBLISHED}},
            {"record_id": "rDraft", "fields": {NF.STATUS: NS.DRAFT_PENDING, NF.PUBLISH_LINK: "http://y"}},
        ]
        with mock.patch.object(feishu_io, "list_records", lambda t: notes):
            ids = [r["record_id"] for r in collect.published_notes()]
        self.assertEqual(ids, ["rP"])  # 只 已发 + 有发布链接


class CollectWriteback(unittest.TestCase):
    def test_writes_back_collected_metrics(self):
        notes = [{"record_id": "rP", "fields": {NS.FIELD: NS.PUBLISHED, NF.PUBLISH_LINK: "http://x"}}]
        updates = []
        with mock.patch.object(feishu_io, "list_records", lambda t: notes), \
                mock.patch.object(metrics, "collect", lambda url, mode: {NF.LIKED: 100, NF.COLLECTED: 20}), \
                mock.patch.object(feishu_io, "update_record", lambda t, rid, f: updates.append((rid, f))):
            s = collect.collect_and_writeback(mode="real")
        self.assertEqual(updates, [("rP", {NF.LIKED: 100, NF.COLLECTED: 20})])
        self.assertEqual(s["写回"], 1)

    def test_stub_writes_nothing(self):
        """stub 采集返 {} → 不写回(零成本,不造假数据)。"""
        notes = [{"record_id": "rP", "fields": {NF.STATUS: NS.PUBLISHED, NF.PUBLISH_LINK: "http://x"}}]
        updates = []
        with mock.patch.object(feishu_io, "list_records", lambda t: notes), \
                mock.patch.object(feishu_io, "update_record", lambda t, rid, f: updates.append((rid, f))):
            s = collect.collect_and_writeback(mode="stub")  # metrics.collect stub 返 {}
        self.assertEqual(updates, [])
        self.assertEqual(s["写回"], 0)

    def test_no_published_no_crash(self):
        with mock.patch.object(feishu_io, "list_records", lambda t: []):
            s = collect.collect_and_writeback(mode="stub")
        self.assertEqual(s, {"采集": 0, "写回": 0})

    def test_link_takes_url_not_text(self):
        """回归(真上线暴露):发布链接是 url 字段 {link,text},取 link 不取 text,
        否则真采集拿到描述文字必挂(实测端到端才发现)。"""
        self.assertEqual(collect._link({"link": "https://xhs/real", "text": "描述文字"}), "https://xhs/real")
        self.assertEqual(collect._link("https://plain"), "https://plain")
        self.assertEqual(collect._link(None), "")

    def test_write_guard_blocks_prod_under_test_mode(self):
        """红线:TEST_MODE 下回流写回也只许测试 Base(闸先抛)。"""
        orig_token, orig_mode = config.BASE_TOKEN, config.TEST_MODE
        try:
            config.BASE_TOKEN = config.PROD_BASE
            config.TEST_MODE = True
            with self.assertRaises(GuardError):
                collect.collect_and_writeback(mode="stub")
        finally:
            config.BASE_TOKEN, config.TEST_MODE = orig_token, orig_mode


if __name__ == "__main__":
    unittest.main()
