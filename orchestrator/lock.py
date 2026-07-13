"""进程级互斥锁(flock,ADR-0009 P1 并发裸奔):防两个自动化写进程并发造重复派活/后写覆盖。

人在飞书里并发编辑安全(Base 是唯一真值、字段级 last-write-wins);此锁只护**自动化写路径**
(dispatch/run_day 这类"读在途→建行"的 TOCTOU)。非阻塞:拿不到锁=另一个写进程在跑→抛 LockBusy 跳过,
不排队不重复。用现成的空文件 locks/orchestrator.lock。
"""
from __future__ import annotations

import contextlib
import fcntl

from . import config

_LOCK_PATH = config.WORKSPACE / "locks" / "orchestrator.lock"


class LockBusy(RuntimeError):
    """另一个自动化写进程正持锁。message 面向告警可读。"""


@contextlib.contextmanager
def write_lock():
    """自动化写路径互斥(非阻塞):拿不到→LockBusy(跳过,防并发重复派活)。人机交互不走此锁。"""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    f = open(_LOCK_PATH, "w")   # noqa: SIM115
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as e:
            raise LockBusy("另一个自动化写进程在跑,本次跳过(防并发重复派活/后写覆盖)") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()
