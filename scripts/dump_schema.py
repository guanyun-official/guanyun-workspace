#!/usr/bin/env python3
"""
dump_schema.py — 用 lark-cli 拉指定 Base 的全部表字段契约,落 schema/。

产出:
  schema/<prod|test>/<表名>.json   每表:{table_id, table_name, fields:[{field_name, type, options?}]}
  schema/<prod|test>/_tables.json  汇总:{base_token, dumped_at, tables:{表名: table_id}}

用法:
  python3 scripts/dump_schema.py                 # 生产 Base → schema/prod/(只读,绝不写 Base)
  python3 scripts/dump_schema.py --base test     # 测试 Base → schema/test/

只读操作(table-list / field-list),对任何 Base 都零写入。
身份:lark-cli --as bot(璃奈)+ LARK_CLI_NO_PROXY=1(见 AGENTS.md 工具清单)。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASES = {
    "prod": "N9IVbi6pTatJG5sqyTTcc0vSn4g",   # 巧荷 Qiaohe-official-beta(生产,14 表)
    "test": "ZhzJbfkOsafwevsWkW8cfoILnfb",   # 测试 Base(复制自生产)
}


def _lark(args: list[str]) -> dict:
    """lark-cli base <args> --as bot,返回解析后的 JSON(ok 校验)。"""
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    r = subprocess.run(["lark-cli", "base", *args, "--as", "bot"],
                       capture_output=True, text=True, env=env, timeout=60)
    out = r.stdout.strip()
    if not out:
        raise RuntimeError(f"lark-cli 空输出: {(r.stderr or '').strip()[:200]}")
    data = json.loads(out)
    if not data.get("ok"):
        raise RuntimeError(f"lark-cli 失败: {data.get('error') or out[:200]}")
    return data


def _field_contract(f: dict) -> dict:
    """从 field-list 一条字段里抽契约:field_name / type / select options(如有)。"""
    c = {"field_name": f.get("name", ""), "type": f.get("type", "")}
    opts = [o.get("name") for o in (f.get("options") or []) if isinstance(o, dict) and o.get("name")]
    if opts:
        c["options"] = opts
    if f.get("link_table"):
        c["link_table"] = f["link_table"]
    return c


def dump(base_key: str) -> int:
    token = BASES[base_key]
    out_dir = ROOT / "schema" / base_key
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = _lark(["+table-list", "--base-token", token])["data"]["tables"]
    summary = {
        "base_token": token,
        "base": base_key,
        "dumped_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "tables": {t["name"]: t["id"] for t in tables},
    }
    for t in tables:
        fields = _lark(["+field-list", "--base-token", token, "--table-id", t["id"]])["data"]["fields"]
        contract = {
            "table_id": t["id"],
            "table_name": t["name"],
            "fields": [_field_contract(f) for f in fields],
        }
        p = out_dir / f"{t['name']}.json"
        p.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  ✓ {base_key}/{t['name']}.json ({len(fields)} 字段)")
    (out_dir / "_tables.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ {base_key}: {len(tables)} 表契约 → {out_dir.relative_to(ROOT)}/")
    return len(tables)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="dump Bitable 表字段契约(只读)")
    ap.add_argument("--base", choices=list(BASES), default="prod")
    args = ap.parse_args()
    try:
        dump(args.base)
    except Exception as e:  # noqa: BLE001
        print(f"❌ dump 失败: {e}", file=sys.stderr)
        sys.exit(1)
