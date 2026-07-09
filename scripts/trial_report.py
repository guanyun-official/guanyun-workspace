#!/usr/bin/env python3
"""P7 一周试运行只读报告。

读取运行日志表 + 笔记表，汇总指定窗口内的推进器活跃度、失败、成本、发布包、发布回执、
待审/待发布队列。默认只报告；加 --require-activity 时把缺 daily/heartbeat 或存在失败作为硬失败。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import feishu_io  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402
from orchestrator.bitable import NoteStatus as NS  # noqa: E402
from orchestrator.bitable import RunLogFields as RLF  # noqa: E402
from orchestrator.bitable import parse_ts, text  # noqa: E402


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _cost(fields: dict) -> float:
    v = fields.get(RLF.COST)
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    detail = str(fields.get(RLF.DETAIL) or "")
    if "cost_cny=" in detail:
        try:
            return float(detail.split("cost_cny=", 1)[1].split()[0])
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def _code(fields: dict) -> str:
    return text(fields.get(NF.CODE)).strip() or "?"


def _parse_since(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("since 必须是 ISO 时间,例如 2026-07-10T09:00") from e


def _window(days: int, now: datetime | None = None, since: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now()
    return since or (end - timedelta(days=days)), end


def summarize_run_logs(records: list[dict], *, since: datetime) -> dict:
    rows = []
    for r in records:
        f = r.get("fields") or {}
        ts = parse_ts(f.get(RLF.TIME))
        if not ts or ts < since:
            continue
        rows.append({
            "ts": ts,
            "action": str(f.get(RLF.ACTION) or ""),
            "result": str(f.get(RLF.RESULT) or ""),
            "summary": str(f.get(RLF.SUMMARY) or ""),
            "cost": _cost(f),
        })
    rows.sort(key=lambda x: x["ts"], reverse=True)
    actions = Counter(r["action"] for r in rows if r["action"])
    failures = [r for r in rows if r["result"] and r["result"] != "成功"]
    daily = [r for r in rows if "daily" in r["action"] or "daily" in r["summary"]]
    heartbeat = [r for r in rows if "heartbeat" in r["action"] or "heartbeat" in r["summary"]]
    packages = [r for r in rows if "发布包" in r["action"] or "发布包" in r["summary"]]
    return {
        "total": len(rows),
        "actions": dict(actions),
        "failures": failures,
        "daily_count": len(daily),
        "heartbeat_count": len(heartbeat),
        "package_count": len(packages),
        "cost_cny": round(sum(r["cost"] for r in rows), 2),
        "latest": rows[0] if rows else None,
    }


def summarize_notes(records: list[dict], *, since: datetime) -> dict:
    status_counts: Counter[str] = Counter()
    published = []
    published_with_link = []
    to_publish = []
    review = []
    approved = []
    for r in records:
        f = r.get("fields") or {}
        status = str(f.get(NF.STATUS) or "")
        status_counts[status] += 1
        code = _code(f)
        if status in {NS.PUBLISHED, NS.LOOPED_BACK}:
            ts = parse_ts(f.get(NF.PUBLISHED_AT))
            if ts and ts >= since:
                published.append(code)
                if text(f.get(NF.PUBLISH_LINK)).strip():
                    published_with_link.append(code)
        elif status == NS.TO_PUBLISH:
            to_publish.append(code)
        elif status == NS.DRAFT_PENDING:
            review.append(code)
        elif status == NS.APPROVED:
            approved.append(code)
    return {
        "status_counts": dict(status_counts),
        "published": published,
        "published_with_link": published_with_link,
        "to_publish": to_publish,
        "review": review,
        "approved": approved,
    }


def build_checks(run_summary: dict, note_summary: dict, *, require_activity: bool) -> list[Check]:
    checks: list[Check] = []
    total = run_summary["total"]
    checks.append(Check(
        "run_logs",
        "PASS" if total else ("FAIL" if require_activity else "WARN"),
        f"{total} records in window; latest={run_summary['latest']['ts']:%Y-%m-%d %H:%M}" if total else "no run logs in window",
    ))
    checks.append(Check(
        "daily",
        "PASS" if run_summary["daily_count"] else ("FAIL" if require_activity else "WARN"),
        f"{run_summary['daily_count']} daily runs",
    ))
    checks.append(Check(
        "heartbeat",
        "PASS" if run_summary["heartbeat_count"] else ("FAIL" if require_activity else "WARN"),
        f"{run_summary['heartbeat_count']} heartbeat runs",
    ))
    failures = run_summary["failures"]
    checks.append(Check(
        "run_failures",
        "FAIL" if failures else "PASS",
        f"{len(failures)} failures" + (f"; latest={failures[0]['summary'][:80]}" if failures else ""),
    ))
    checks.append(Check("cost", "PASS", f"¥{run_summary['cost_cny']:.2f} in window"))
    checks.append(Check("packages", "PASS", f"{run_summary['package_count']} package log entries"))
    published = note_summary["published"]
    with_link = note_summary["published_with_link"]
    receipt_status = "PASS" if len(with_link) == len(published) else "WARN"
    checks.append(Check(
        "publish_receipts",
        receipt_status,
        f"{len(with_link)}/{len(published)} published notes have links in window",
    ))
    checks.append(Check("review_queue", "PASS", f"{len(note_summary['review'])} 草稿待发; {len(note_summary['approved'])} 已批准; {len(note_summary['to_publish'])} 待发布"))
    return checks


def build_report(
    *,
    days: int,
    require_activity: bool,
    list_records: Callable[[str], list[dict]] = feishu_io.list_records,
    now: datetime | None = None,
    since: datetime | None = None,
) -> dict:
    since_dt, end = _window(days, now, since)
    run_summary = summarize_run_logs(list_records("运行日志表"), since=since_dt)
    note_summary = summarize_notes(list_records("笔记表"), since=since_dt)
    checks = build_checks(run_summary, note_summary, require_activity=require_activity)
    return {
        "window": {
            "since": since_dt.isoformat(timespec="seconds"),
            "until": end.isoformat(timespec="seconds"),
            "days": days,
            "mode": "since" if since else f"last_{days}_days",
        },
        "checks": [asdict(c) for c in checks],
        "run_summary": {
            "total": run_summary["total"],
            "actions": run_summary["actions"],
            "daily_count": run_summary["daily_count"],
            "heartbeat_count": run_summary["heartbeat_count"],
            "package_count": run_summary["package_count"],
            "cost_cny": run_summary["cost_cny"],
        },
        "note_summary": note_summary,
    }


def _print_human(report: dict) -> None:
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    w = report["window"]
    print(f"P7 试运行报告({w['mode']} {w['since']} → {w['until']})")
    for c in report["checks"]:
        print(f"  {icon.get(c['status'], '?')} {c['name']}: {c['detail']}")
    actions = report["run_summary"]["actions"]
    if actions:
        print("  actions:", ", ".join(f"{k}={v}" for k, v in sorted(actions.items())))
    if any(c["status"] == "FAIL" for c in report["checks"]):
        print("\n❌ 试运行报告有 FAIL；先处理再放量")
    else:
        print("\n✅ 试运行报告无 FAIL；WARN 需人工判断是否符合当前阶段")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since", type=_parse_since, help="ISO 起点时间,例如 2026-07-10T09:00；用于从 cron 安装时刻开始复盘")
    ap.add_argument("--require-activity", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = build_report(days=args.days, since=args.since, require_activity=args.require_activity)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return 1 if any(c["status"] == "FAIL" for c in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
