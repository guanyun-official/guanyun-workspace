"""飞书 IO(推进器专用薄层):单 writer 串行、429 指数退避、显式报错(绝不静默 {})。
所有写操作先过 guard.assert_base_allowed —— TEST_MODE 下物理到不了生产。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime

from . import config, guard
from .bitable import RunLogFields as RLF


class FeishuIOError(RuntimeError):
    pass


def _call(method: str, path: str, params: dict | None = None, data: dict | None = None) -> dict:
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    args = ["lark-cli", "api", method, path, "--as", "bot"]
    if params:
        args += ["--params", json.dumps(params, ensure_ascii=False)]
    if data:
        args += ["--data", json.dumps(data, ensure_ascii=False)]
    delay = 1.0
    for attempt in range(5):
        r = subprocess.run(args, capture_output=True, text=True, cwd=str(config.WORKSPACE), env=env, timeout=60)
        out = r.stdout.strip()
        if "{" in out:
            try:
                d = json.loads(out[out.find("{"):])
            except json.JSONDecodeError:
                raise FeishuIOError(f"非 JSON 响应: {out[:200]}")
            code = d.get("code", d.get("error", {}).get("code"))
            if code == 0:
                return d.get("data", {})
            if code in (99991400, 1254290, 429) or "frequency" in str(d)[:300].lower():
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            raise FeishuIOError(f"{method} {path} code={code}: {str(d)[:300]}")
        time.sleep(delay)
        delay = min(delay * 2, 16)
    raise FeishuIOError(f"{method} {path} 5 次重试未成功")


def _guard_write() -> None:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)


def list_records(table_name: str, page_size: int = 100) -> list[dict]:
    tid = config.tables()[table_name]
    items, token = [], None
    while True:
        params = {"page_size": page_size}
        if token:
            params["page_token"] = token
        d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records", params)
        items += d.get("items") or []
        if not d.get("has_more"):
            return items
        token = d.get("page_token")


def update_record(table_name: str, record_id: str, fields: dict) -> None:
    _guard_write()
    tid = config.tables()[table_name]
    _call("PUT", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{record_id}",
          data={"fields": fields})


def create_record(table_name: str, fields: dict) -> str:
    _guard_write()
    tid = config.tables()[table_name]
    d = _call("POST", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records",
              data={"fields": fields})
    return d["record"]["record_id"]


def delete_record(table_name: str, record_id: str) -> None:
    _guard_write()
    tid = config.tables()[table_name]
    _call("DELETE", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{record_id}")


def log_run(summary: str, action: str, result: str = "成功", *, skill: str = "", note_ref: str = "",
            table: str = "笔记表", detail: str = "") -> None:
    """写运行日志表(9 字段契约)。日志失败只打印不阻断主流程。"""
    try:
        create_record("运行日志表", {
            RLF.SUMMARY: summary,
            RLF.TIME: int(datetime.now().timestamp() * 1000),
            RLF.EXECUTOR: "orchestrator",
            RLF.SKILL: skill,
            RLF.ACTION: action,
            RLF.TABLE_REF: table,
            RLF.RECORD_REF: note_ref,
            RLF.RESULT: result,
            RLF.DETAIL: detail[:800],
        })
    except Exception as e:  # noqa: BLE001
        print(f"[log_run 降级] {e}")
