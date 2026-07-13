"""进程级并发锁(lock.write_lock):防自动化写路径并发(ADR-0009)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import lock  # noqa: E402


class TestWriteLock(unittest.TestCase):
    def test_excludes_concurrent(self):
        with lock.write_lock():
            with self.assertRaises(lock.LockBusy):   # 已持锁→再拿抛 LockBusy(跳过防并发)
                with lock.write_lock():
                    pass

    def test_reacquire_after_release(self):
        with lock.write_lock():
            pass
        with lock.write_lock():                       # 释放后能再拿
            pass


if __name__ == "__main__":
    unittest.main()
