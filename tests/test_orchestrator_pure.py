"""P4 纯函数层单测:runbook 路由 + guard 硬闸。零网络零写入。"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, guard
from orchestrator.runbook import Action, route

NOW = datetime(2026, 7, 8, 12, 0)
MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731


class TestRunbook(unittest.TestCase):
    def test_full_lifecycle_routing(self):
        cases = {
            "想法储备": Action.LIST_IDEA,
            "待拍素材": Action.REMIND_SHOOT,
            "待出文案": Action.GEN_COPY,
            "已批准": Action.ASSEMBLE_PACKAGE,
            "暂缓归档": Action.NOOP,
            "已回流": Action.NOOP,
        }
        for state, want in cases.items():
            self.assertIs(route({"状态": state}, NOW), want, state)

    def test_review_wait_then_overdue(self):
        fresh = {"状态": "草稿待发", "_state_changed_at": MS(datetime(2026, 7, 8, 11, 0))}
        self.assertIs(route(fresh, NOW), Action.NOOP)
        stale = {"状态": "草稿待发", "_state_changed_at": MS(datetime(2026, 7, 6, 11, 0))}
        self.assertIs(route(stale, NOW), Action.REMIND_REVIEW)

    def test_pending_publish_detects_backfill(self):
        self.assertIs(route({"状态": "待发布"}, NOW), Action.NOOP)
        self.assertIs(route({"状态": "待发布", "发布链接": {"link": "https://x"}}, NOW), Action.MARK_PUBLISHED)

    def test_published_metrics_then_close(self):
        recent = {"状态": "已发", "实际发布日": MS(datetime(2026, 7, 6))}
        self.assertIs(route(recent, NOW), Action.COLLECT_METRICS)
        old = {"状态": "已发", "实际发布日": MS(datetime(2026, 6, 25))}
        self.assertIs(route(old, NOW), Action.CLOSE_LOOP)

    def test_unknown_state_noop(self):
        self.assertIs(route({"状态": "奇怪状态"}, NOW), Action.NOOP)
        self.assertIs(route({}, NOW), Action.NOOP)


class TestGuard(unittest.TestCase):
    def test_base_guard_test_mode(self):
        guard.assert_base_allowed(config.TEST_BASE, test_mode=True)  # 不抛
        with self.assertRaises(guard.GuardError):
            guard.assert_base_allowed(config.PROD_BASE, test_mode=True)  # 测试模式拒生产
        with self.assertRaises(guard.GuardError):
            guard.assert_base_allowed("", test_mode=True)

    def test_base_guard_prod_mode_only_known_prod(self):
        guard.assert_base_allowed(config.PROD_BASE, test_mode=False)
        with self.assertRaises(guard.GuardError):
            guard.assert_base_allowed("appRANDOM123", test_mode=False)

    def test_ai_declaration_gate(self):
        guard.assert_ai_declared({"AI声明": True, "排期编号": "PQ-1"})
        with self.assertRaises(guard.GuardError):
            guard.assert_ai_declared({"AI声明": False, "排期编号": "PQ-1"})
        with self.assertRaises(guard.GuardError):
            guard.assert_ai_declared({"排期编号": "PQ-1"})

    def test_publish_quota(self):
        guard.assert_publish_quota(0)
        guard.assert_publish_quota(config.PER_ACCOUNT_DAILY_PUBLISH - 1)
        with self.assertRaises(guard.GuardError):
            guard.assert_publish_quota(config.PER_ACCOUNT_DAILY_PUBLISH)

    def test_copy_quota(self):
        self.assertTrue(guard.copy_quota_left(0))
        self.assertFalse(guard.copy_quota_left(config.DAILY_COPY_LIMIT))


if __name__ == "__main__":
    unittest.main()
