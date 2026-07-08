"""排产提议纯逻辑:已排过的衣服不再提议、素材齐排前。mock 表,零网络。"""
import sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def _rec(fields): return {"fields": fields, "record_id": "r"}

class TestPlanDay(unittest.TestCase):
    def test_proposal_excludes_used_and_ranks_ready(self):
        import scripts.plan_day as pd
        tables = {
            "账号表":[_rec({"账号名":"科普号","上线状态":"launch先上"}),
                     _rec({"账号名":"官号","上线状态":"远期"})],  # 远期不提议
            "衣服总表":[_rec({"衣服编号":"GY-001","款式名称":"甲"}),
                       _rec({"衣服编号":"GY-002","款式名称":"乙"}),
                       _rec({"衣服编号":"GY-003","款式名称":"丙"})],
            "笔记表":[_rec({"关联衣服":"GY-001","账号(自动)":"科普号","状态":"已发"})],  # GY-001已发→排除
            "素材表":[_rec({"拍摄状态":"已拍","关联衣服":"GY-003"})],  # GY-003素材齐
        }
        with mock.patch.object(pd.feishu_io,"list_records",side_effect=lambda t:tables[t]):
            plan = pd.propose()
        self.assertIn("科普号", plan)
        self.assertNotIn("官号", plan)                       # 远期号不提议
        skus=[c["sku"] for c in plan["科普号"]]
        self.assertNotIn("GY-001", skus)                     # 已发的排除
        self.assertEqual(plan["科普号"][0]["sku"], "GY-003")  # 素材齐的排最前
        self.assertEqual(plan["科普号"][0]["素材就绪"], 1)
