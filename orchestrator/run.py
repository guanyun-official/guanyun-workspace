"""推进器 CLI 入口。
用法:
  python3 -m orchestrator.run --mode daily            # 每日排产轮(日报)
  python3 -m orchestrator.run --mode heartbeat        # 巡检轮(催办/推进/收口)
  --llm real   真实生成文案(默认 stub 占位,零成本)
  --limit N    本轮最多处理 N 条笔记(默认 20)
"""
from __future__ import annotations

import argparse
import json

from . import config
from .engine import run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "heartbeat"], default="heartbeat")
    ap.add_argument("--llm", choices=["stub", "real"], default="stub")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} mode={a.mode} llm={a.llm}")
    s = run(mode=a.mode, llm_mode=a.llm, limit=a.limit)
    print(json.dumps(s, ensure_ascii=False, default=str, indent=1))
    return 1 if s.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
