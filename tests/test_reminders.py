"""F1 提醒节流单测。用临时 state 文件,不碰真状态。"""
import sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import reminders

D1 = datetime(2026, 7, 8, 9, 0)
D1b = datetime(2026, 7, 8, 20, 0)  # 同日晚些
D2 = datetime(2026, 7, 9, 9, 0)    # 次日

class TestThrottle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "rs.json"
        reminders.STATE_FILE = self.tmp
    def test_once_per_day(self):
        self.assertTrue(reminders.should_remind("recX", "shoot", D1))
        reminders.mark("recX", "shoot", D1)
        self.assertFalse(reminders.should_remind("recX", "shoot", D1b))  # 同日不再提醒
        self.assertTrue(reminders.should_remind("recX", "shoot", D2))    # 次日恢复
    def test_kind_and_record_isolated(self):
        reminders.mark("recX", "shoot", D1)
        self.assertTrue(reminders.should_remind("recX", "review", D1))   # 不同类型独立
        self.assertTrue(reminders.should_remind("recY", "shoot", D1))    # 不同记录独立

if __name__ == "__main__":
    unittest.main()
