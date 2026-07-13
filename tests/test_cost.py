"""月度成本核算 + 告警(cost.py):读运行日志成本_元当月求和,超阈告警。零网络(注入records/today)。"""
import sys
import unittest
from datetime import date, datetime
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, cost  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF  # noqa: E402


def _ms(y, m, d):
    return int(datetime(y, m, d, 9, 0).timestamp() * 1000)


class TestCost(unittest.TestCase):
    def test_monthly_sums_current_month_only(self):
        recs = [
            {"fields": {RLF.TIME: _ms(2026, 7, 5), RLF.COST: 2.5}},
            {"fields": {RLF.TIME: _ms(2026, 7, 20), RLF.COST: "1.5"}},   # str 也认
            {"fields": {RLF.TIME: _ms(2026, 6, 30), RLF.COST: 100}},     # 上月不算
            {"fields": {RLF.TIME: _ms(2026, 7, 1), RLF.COST: "坏值"}},    # 坏值当0
        ]
        self.assertEqual(cost.monthly_cost_cny(recs, date(2026, 7, 15)), 4.0)   # 2.5+1.5

    def test_budget_alert_over_and_under(self):
        recs = [{"fields": {RLF.TIME: _ms(2026, 7, 5), RLF.COST: 500}}]
        with mock.patch.object(config, "BUDGET_MONTHLY_CNY", 300.0):
            self.assertTrue(cost.budget_alert(recs, date(2026, 7, 15)))          # 500≥300→告警
        with mock.patch.object(config, "BUDGET_MONTHLY_CNY", 1000.0):
            self.assertEqual(cost.budget_alert(recs, date(2026, 7, 15)), "")     # 500<1000→无


if __name__ == "__main__":
    unittest.main()
