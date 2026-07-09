#!/usr/bin/env python3
"""P7 有限试运行冒烟。

不安装 crontab；按 cron 等价顺序跑一轮:

1. 运营预检
2. daily(stub/real, 默认 stub;默认会物化今日排产)
3. heartbeat(stub/real)
4. 备份
5. cron 状态只读巡检
6. 从本次起点生成 trial_report

默认 `ALERT_DRY_RUN=1`，避免冒烟时向飞书群投递；但 daily/heartbeat 仍会按真实引擎写入
运营库/测试 Base。生产 Base 由 preflight + engine guard 拦截。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config  # noqa: E402
from scripts import cron_status, preflight_operational, trial_report  # noqa: E402


@dataclass
class Step:
    name: str
    status: str
    detail: str


def _status_has_fail(items: list[dict] | list[Step]) -> bool:
    for item in items:
        status = item.status if isinstance(item, Step) else item.get("status")
        if status == "FAIL":
            return True
    return False


def _run_command(
    name: str,
    args: list[str],
    *,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 600,
) -> Step:
    proc = runner(
        args,
        cwd=config.WORKSPACE,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = proc.stdout or proc.stderr or ""
    detail = _summarize_command_output(output, proc.returncode)
    obj = _extract_json_object(output)
    skipped = isinstance(obj, dict) and obj.get("skipped")
    return Step(name, "PASS" if proc.returncode == 0 and not skipped else "FAIL", detail)


def _extract_json_object(output: str) -> object | None:
    raw = output.strip()
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _summarize_command_output(output: str, returncode: int) -> str:
    raw = output.strip()
    if not raw:
        return f"exit={returncode}"
    obj = _extract_json_object(raw)
    if isinstance(obj, dict) and obj.get("skipped"):
        return f"skipped={obj.get('skipped')}"
    if isinstance(obj, dict) and "mode" in obj:
        planning = obj.get("planning") or {}
        parts = [
            f"mode={obj.get('mode')}",
            f"actions={len(obj.get('actions') or [])}",
            f"errors={len(obj.get('errors') or [])}",
        ]
        if planning:
            parts.append(f"planning_created={planning.get('created', 0)}")
            parts.append(f"planning_existing={planning.get('existing', 0)}")
        return " ".join(parts)
    lines = [line for line in raw.splitlines() if line.strip() and line.strip() not in {"}", "]"}]
    return (lines[-1] if lines else raw.splitlines()[-1])[:180]


def build_report_step(report: dict) -> Step:
    failures = [c for c in report["checks"] if c["status"] == "FAIL"]
    run = report["run_summary"]
    detail = (
        f"daily={run['daily_count']} heartbeat={run['heartbeat_count']} "
        f"failures={len(failures)} cost=¥{run['cost_cny']:.2f}"
    )
    return Step("trial_report", "FAIL" if failures else "PASS", detail)


def run_smoke(
    *,
    llm: str,
    limit: int,
    skip_plan: bool,
    real_alerts: bool,
    now: datetime | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    start = now or datetime.now()
    env = dict(os.environ)
    if not real_alerts:
        env["ALERT_DRY_RUN"] = "1"

    preflight_checks = preflight_operational.run_checks(llm)
    steps = [
        Step(
            "preflight",
            "FAIL" if _status_has_fail([asdict(c) for c in preflight_checks]) else "PASS",
            "; ".join(f"{c.name}={c.status}" for c in preflight_checks),
        )
    ]

    daily_args = [sys.executable, "-m", "orchestrator.run", "--mode", "daily", "--llm", llm, "--limit", str(limit)]
    if skip_plan:
        daily_args.append("--skip-plan")
    steps.append(_run_command("daily", daily_args, env=env, runner=runner))
    steps.append(_run_command(
        "heartbeat",
        [sys.executable, "-m", "orchestrator.run", "--mode", "heartbeat", "--llm", llm, "--limit", str(limit)],
        env=env,
        runner=runner,
    ))
    steps.append(_run_command("backup", [sys.executable, "scripts/backup_tables.py"], env=env, runner=runner))

    cron_checks = cron_status.run_checks(require_installed=False, within_hours=1)
    steps.append(Step(
        "cron_status",
        "FAIL" if _status_has_fail([asdict(c) for c in cron_checks]) else "PASS",
        "; ".join(f"{c.name}={c.status}" for c in cron_checks),
    ))

    report = trial_report.build_report(days=7, since=start, require_activity=True)
    steps.append(build_report_step(report))

    return {
        "start": start.isoformat(timespec="seconds"),
        "llm": llm,
        "limit": limit,
        "skip_plan": skip_plan,
        "alerts": "real" if real_alerts else "dry",
        "steps": [asdict(s) for s in steps],
        "preflight_checks": [asdict(c) for c in preflight_checks],
        "cron_checks": [asdict(c) for c in cron_checks],
        "trial_report": report,
    }


def _print_human(result: dict) -> None:
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    print(f"P7 有限试运行冒烟(start={result['start']} llm={result['llm']} alerts={result['alerts']})")
    if result["skip_plan"]:
        print("  注意: daily 使用 --skip-plan；未覆盖真实排产物化")
    for s in result["steps"]:
        print(f"  {icon.get(s['status'], '?')} {s['name']}: {s['detail']}")
    if any(s["status"] == "FAIL" for s in result["steps"]):
        print("\n❌ 冒烟失败:先处理 FAIL 项")
    else:
        print("\n✅ 冒烟无 FAIL；如用于正式试运行,记录 start 并一周后用 trial_report --since 复盘")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["stub", "real"], default="stub")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--skip-plan", action="store_true", help="诊断用:daily 跳过排产物化；正式冒烟不建议")
    ap.add_argument("--real-alerts", action="store_true", help="冒烟时允许真实 hermes/飞书告警；默认 dry-run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = run_smoke(llm=args.llm, limit=args.limit, skip_plan=args.skip_plan, real_alerts=args.real_alerts)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(result)
    return 1 if any(s["status"] == "FAIL" for s in result["steps"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
