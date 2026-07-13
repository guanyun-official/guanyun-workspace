"""Base 守卫白名单 = 多品牌注册表(config.BRAND_BASES / known_bases)。

红线:TEST_MODE 只许写已登记品牌的测试 Base;生产必须显式 TEST_MODE=0 且属已登记生产 Base。
接口留出:目前仅巧荷;加品牌 = BRAND_BASES 加一行即自动放行其 Base(本测试证明这条扩展路径真通)。
"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, guard  # noqa: E402
from orchestrator.guard import GuardError  # noqa: E402


class TestBaseWhitelist(unittest.TestCase):
    def test_qiaohe_single_brand_behavior_unchanged(self):
        guard.assert_base_allowed(config.TEST_BASE, test_mode=True)      # 巧荷测试库:放行
        guard.assert_base_allowed(config.PROD_BASE, test_mode=False)     # 巧荷生产库(显式非测试):放行
        with self.assertRaises(GuardError):
            guard.assert_base_allowed(config.PROD_BASE, test_mode=True)  # 测试模式写生产:拒
        with self.assertRaises(GuardError):
            guard.assert_base_allowed(config.TEST_BASE, test_mode=False)  # 非测试模式写测试库:拒(不属生产白名单)

    def test_empty_token_rejected(self):
        with self.assertRaises(GuardError):
            guard.assert_base_allowed("", test_mode=True)

    def test_unknown_base_rejected(self):
        with self.assertRaises(GuardError):
            guard.assert_base_allowed("bogusUnregisteredBaseToken", test_mode=True)

    def test_registering_second_brand_whitelists_its_base(self):
        # 接口留出:注册表加第 2 品牌 → 其 Base 自动进白名单(不改 guard 代码)
        extended = {**config.BRAND_BASES, "测试品牌B": {"test": "brandB_test_base", "prod": "brandB_prod_base"}}
        with mock.patch.object(config, "BRAND_BASES", extended):
            guard.assert_base_allowed("brandB_test_base", test_mode=True)     # 新品牌测试库放行
            guard.assert_base_allowed("brandB_prod_base", test_mode=False)    # 新品牌生产库放行
            guard.assert_base_allowed(config.TEST_BASE, test_mode=True)       # 巧荷仍放行(不互斥)

    def test_known_bases_registry(self):
        self.assertEqual(config.known_bases("test"), {config.TEST_BASE})     # 目前仅巧荷
        self.assertEqual(config.known_bases("prod"), {config.PROD_BASE})


if __name__ == "__main__":
    unittest.main()
