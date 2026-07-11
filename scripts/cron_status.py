#!/usr/bin/env python3
"""运营 cron 运行态只读巡检。

用于 P7 挂 cron 后检查:crontab 标记块、日志文件、备份目录、运行日志表最近记录。
默认安装前也可运行(未安装为 WARN);加 --require-installed 后未安装/结构异常会失败。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF, parse_ts  # noqa: E402

MARK_BEGIN = "# BEGIN guanyun-orchestrator"
MARK_END = "# END guanyun-orchestrator"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _marked_block(text: str) -> str:
    if MARK_BEGIN not in text or MARK_END not in text:
        return ""
    return text.split(MARK_BEGIN, 1)[1].split(MARK_END, 1)[0]


def check_crontab(
    *,
    require_installed: bool = False,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Check:
    proc = runner(["crontab", "-l"], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        return Check("crontab", "FAIL" if require_installed else "WARN", "crontab 不可读或为空")
    block = _marked_block(proc.stdout)
    if not block:
        return Check("crontab", "FAIL" if require_installed else "WARN", "未安装 guanyun-orchestrator 标记块")
    # 大刀阔斧后重引擎已删,cron 不再有 orchestrator.run daily/heartbeat;只校数据安全底线=每日备份。
    has_backup = "backup_tables.py" in block
    if not has_backup:
        return Check("crontab", "FAIL", "标记块缺 backup_tables cron(数据安全底线)")
    has_weekly = "claude -p" in block
    return Check("crontab", "PASS", f"installed backup={has_backup} weekly={has_weekly}")


def check_local_logs(log_dir: Path = config.WORKSPACE / "logs") -> Check:
    files = [p for p in (log_dir / "cron.log", log_dir / "weekly.log") if p.exists()]
    if not files:
        return Check("local_logs", "WARN", "logs/cron.log 与 logs/weekly.log 均不存在")
    details = []
    for p in files:
        size = p.stat().st_size
        detail = f"{p.name}:{size}B"
        if size:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            detail += f" last={lines[-1][:80] if lines else '<empty>'}"
        details.append(detail)
    return Check("local_logs", "PASS", "; ".join(details))


def check_backups(root: Path = config.WORKSPACE / "backups") -> Check:
    dirs = sorted([p for p in root.glob("test-*") if p.is_dir()])
    if not dirs:
        return Check("backups", "WARN", "未发现 backups/test-*")
    latest = dirs[-1]
    n = len(list(latest.glob("*.json")))
    status = "PASS" if n >= 5 else "WARN"
    return Check("backups", status, f"{latest.name} json_files={n}")


def check_run_logs(
    *,
    within_hours: int = 24,
    list_records: Callable[[str], list[dict]] = feishu_io.list_records,
    now: datetime | None = None,
) -> Check:
    now = now or datetime.now()
    rows = []
    for r in list_records("运行日志表"):
        f = r.get("fields") or {}
        ts = parse_ts(f.get(RLF.TIME))
        if ts:
            rows.append((ts, str(f.get(RLF.ACTION) or ""), str(f.get(RLF.RESULT) or ""), str(f.get(RLF.SUMMARY) or "")))
    if not rows:
        return Check("run_logs", "WARN", "运行日志表无可解析时间记录")
    rows.sort(key=lambda x: x[0], reverse=True)
    latest = rows[0]
    age = now - latest[0]
    recent = age <= timedelta(hours=within_hours)
    detail = f"latest={latest[0]:%Y-%m-%d %H:%M} age_h={age.total_seconds()/3600:.1f} action={latest[1]} result={latest[2]} summary={latest[3][:80]}"
    return Check("run_logs", "PASS" if recent else "WARN", detail)


def run_checks(require_installed: bool, within_hours: int) -> list[Check]:
    return [
        check_crontab(require_installed=require_installed),
        check_local_logs(),
        check_backups(),
        check_run_logs(within_hours=within_hours),
    ]


def _print_human(checks: list[Check]) -> None:
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    print("运营 cron 状态巡检")
    for c in checks:
        print(f"  {icon.get(c.status, '?')} {c.name}: {c.detail}")
    if any(c.status == "FAIL" for c in checks):
        print("\n❌ 状态异常:先处理 FAIL 项")
    else:
        print("\n✅ 无 FAIL；WARN 表示未安装或证据不足,需结合当前阶段判断")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-installed", action="store_true")
    ap.add_argument("--within-hours", type=int, default=24)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks = run_checks(args.require_installed, args.within_hours)
    if args.json:
        print(json.dumps([asdict(c) for c in checks], ensure_ascii=False, indent=2))
    else:
        _print_human(checks)
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
