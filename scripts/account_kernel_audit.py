#!/usr/bin/env python3
"""只读审计 AccountKernel 的 SourceOwnership 漂移。

检查 Base「账号表/内容类型表」与 workspace `brands/<brand>/accounts/*.md`
是否存在双真相源。默认只读；发现 FAIL 返回非零，便于 heartbeat / issue 流程捕获。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import account_kernel  # noqa: E402


def _print_human(audit: dict) -> None:
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}
    print(f"AccountKernel 审计(brand={audit['brand']})")
    for c in audit["checks"]:
        print(f"  {icon.get(c['status'], '?')} {c['name']}: {c['detail']}")
    print(f"  Base accounts: {', '.join(a['name'] for a in audit['base_accounts']) or '-'}")
    print(f"  Workspace accounts: {', '.join(a['name'] for a in audit['workspace_accounts']) or '-'}")
    if account_kernel.has_failures(audit):
        print("\n❌ AccountKernel 有 FAIL；先修复 SourceOwnership 再继续填表或排产")
    else:
        print("\n✅ AccountKernel 无 FAIL；WARN 需按当前运营阶段判断")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="观云")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    audit = account_kernel.build_audit(brand=args.brand)
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        _print_human(audit)
    return 1 if account_kernel.has_failures(audit) else 0


if __name__ == "__main__":
    raise SystemExit(main())
