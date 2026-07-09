import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestCheckP5Contract(unittest.TestCase):
    def test_alert_dry_run_is_an_explicit_passing_mode(self):
        """全量验收常用 ALERT_DRY_RUN=1,不能把 dry 投递误判为 hermes 实发失败。"""
        src = (ROOT / "scripts" / "check_p5.sh").read_text(encoding="utf-8")

        self.assertIn('ALERT_DRY_RUN:-0', src)
        self.assertIn('alert:dry', src)
        self.assertIn('dry-run 投递链路可见', src)
        self.assertLess(src.index('ALERT_DRY_RUN:-0'), src.index('hermes→飞书 实发成功'))


if __name__ == "__main__":
    unittest.main()
