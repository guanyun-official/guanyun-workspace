#!/usr/bin/env python3
"""P7 运营库挂 cron 前只读预检。

不安装 cron、不写 Base。检查目标 Base/TEST_MODE、cron 预览、当前 crontab 状态、压测残留、
hermes 可用性等容易在试运行前被忽略的条件。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402

RESIDUAL_PREFIXES = ("_SIM-", "_UAT", "_STRESS-")
MARK_BEGIN = "# BEGIN guanyun-orchestrator"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _code_of(fields: dict) -> str:
    v = fields.get("排期编号")
    if isinstance(v, list):
        return "".join(x.get("text", "") for x in v if isinstance(x, dict))
    return str(v or "")


def check_environment() -> list[Check]:
    checks = []
    checks.append(Check(
        "base_token",
        "PASS" if config.BASE_TOKEN == config.TEST_BASE else "FAIL",
        f"current={config.BASE_TOKEN or '<empty>'} expected={config.TEST_BASE}",
    ))
    checks.append(Check(
        "test_mode",
        "PASS" if config.TEST_MODE else "FAIL",
        f"TEST_MODE={int(config.TEST_MODE)}",
    ))
    checks.append(Check(
        "env_name",
        "PASS" if config.ENV_NAME == "test" else "FAIL",
        f"ENV_NAME={config.ENV_NAME}",
    ))
    return checks


def check_cron_preview(
    llm: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Check:
    proc = runner(
        ["bash", "scripts/install_cron.sh", "--llm", llm],
        cwd=config.WORKSPACE,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        return Check("cron_preview", "FAIL", (proc.stderr or proc.stdout).strip()[:300])
    out = proc.stdout
    ok = f"--mode daily --llm {llm}" in out and f"--mode heartbeat --llm {llm}" in out
    return Check("cron_preview", "PASS" if ok else "FAIL", f"llm={llm}")


def check_crontab_state(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Check:
    proc = runner(["crontab", "-l"], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        return Check("crontab_state", "PASS", "未发现现有 crontab 或 crontab 不可读; install 会创建标记块")
    installed = MARK_BEGIN in proc.stdout
    return Check(
        "crontab_state",
        "WARN" if installed else "PASS",
        "guanyun-orchestrator 已存在; --install 会替换标记块" if installed else "未安装 guanyun-orchestrator 标记块",
    )


def check_residuals(list_records: Callable[[str], list[dict]] = feishu_io.list_records) -> Check:
    rows = []
    for r in list_records("笔记表"):
        fields = r.get("fields") or {}
        code = _code_of(fields)
        if code.startswith(RESIDUAL_PREFIXES):
            rows.append(f"{code}:{fields.get('状态')}")
    if rows:
        return Check("stress_residuals", "FAIL", f"{len(rows)} residuals: {rows[:8]}")
    return Check("stress_residuals", "PASS", "0 residuals for _SIM/_UAT/_STRESS")


def check_hermes(which: Callable[[str], str | None] = shutil.which) -> Check:
    path = which("hermes")
    if path:
        return Check("hermes", "PASS", path)
    return Check("hermes", "WARN", "未找到 hermes；告警会降级 stdout，运营提醒可能不可达")


def run_checks(llm: str) -> list[Check]:
    checks = []
    checks.extend(check_environment())
    checks.append(check_cron_preview(llm))
    checks.append(check_crontab_state())
    checks.append(check_residuals())
    checks.append(check_hermes())
    return checks


def _print_human(checks: list[Check], llm: str) -> None:
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    print(f"P7 运营库 cron 预检(llm={llm})")
    for c in checks:
        print(f"  {icon.get(c.status, '?')} {c.name}: {c.detail}")
    if any(c.status == "FAIL" for c in checks):
        print("\n❌ 预检失败:修复 FAIL 项后再考虑 --install")
    else:
        print(f"\n✅ 预检通过:可进入人工选择窗口后执行 scripts/install_cron.sh --llm {llm} --install")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["stub", "real"], default="stub")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks = run_checks(args.llm)
    if args.json:
        print(json.dumps([asdict(c) for c in checks], ensure_ascii=False, indent=2))
    else:
        _print_human(checks, args.llm)
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
