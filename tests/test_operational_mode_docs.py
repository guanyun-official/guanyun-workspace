import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestOperationalModeDocs(unittest.TestCase):
    def test_p7_checklist_uses_operational_base_not_production_switch(self):
        """P7 上线文档必须体现 2026-07-09 澄清:上线=ZhzJbf 挂 cron,不切 N9IV。"""
        text = (ROOT / "docs" / "P7_上线检查单.md").read_text(encoding="utf-8")

        self.assertIn("ZhzJbfkOsafwevsWkW8cfoILnfb", text)
        self.assertIn("TEST_MODE=1", text)
        self.assertIn("preflight_operational.py --llm stub", text)
        self.assertIn("cron_status.py --require-installed", text)
        self.assertIn("--llm stub --install", text)
        self.assertIn("--llm real --install", text)
        self.assertNotIn("生产token", text)
        self.assertNotIn("TEST_MODE=0", text)
        self.assertNotIn("migrate_p2_to_prod.py --apply", text)

    def test_plan_marks_production_base_readonly_for_current_launch(self):
        text = (ROOT / "docs" / "PLAN.md").read_text(encoding="utf-8")

        self.assertIn("历史名为“测试 Base”，但当前承担运营库", text)
        self.assertIn("只读、焊死不碰", text)
        self.assertIn("不切 `N9IVbi`，不改 `TEST_MODE=0`", text)

    def test_historical_migration_docs_are_not_current_launch_steps(self):
        migration = (ROOT / "docs" / "MIGRATION_P2.md").read_text(encoding="utf-8")
        script = (ROOT / "scripts" / "migrate_p2_to_prod.py").read_text(encoding="utf-8")

        self.assertIn("历史迁移清单", migration)
        self.assertIn("不作为当前上线步骤", migration)
        self.assertIn("不属于当前 P7 上线路径", script)


if __name__ == "__main__":
    unittest.main()
