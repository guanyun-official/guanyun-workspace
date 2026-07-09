"""推进器 CLI 入口。
用法:
  python3 -m orchestrator.run --mode daily            # 每日排产轮(日报)
  python3 -m orchestrator.run --mode heartbeat        # 巡检轮(催办/推进/收口)
  --llm real   真实生成文案(默认 stub 占位,零成本)
  --limit N    本轮最多处理 N 条笔记(默认 20)
  --skip-plan  daily 时跳过排产物化(仅验收/诊断用;cron 不应传)
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
    ap.add_argument("--skip-plan", action="store_true")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} mode={a.mode} llm={a.llm}")
    planning = None
    if a.mode == "daily" and not a.skip_plan:
        from scripts.planner import materialize_day
        planning = materialize_day()
    s = run(mode=a.mode, llm_mode=a.llm, limit=a.limit)
    if planning is not None:
        s["planning"] = planning
        s.setdefault("errors", []).extend(f"排产:{e}" for e in planning.get("errors", []))
    print(json.dumps(s, ensure_ascii=False, default=str, indent=1))
    return 1 if s.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
