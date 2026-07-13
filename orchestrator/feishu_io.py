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


def upload_media(local_path: str, file_name: str = "") -> str:
    """上传媒体到飞书(bitable 附件用),返回 file_token。用于素材缩略图。
    lark-cli 沙盒只认 workspace 内路径 → 先拷进 workspace 临时目录再传(--file multipart),传完清理。"""
    import shutil
    import uuid
    from pathlib import Path
    src = Path(local_path)
    if not src.exists():
        raise FeishuIOError(f"上传媒体:文件不存在 {local_path}")
    tmpdir = config.WORKSPACE / ".media_upload"
    tmpdir.mkdir(exist_ok=True)
    staged = tmpdir / f"{uuid.uuid4().hex}{src.suffix or '.jpg'}"
    shutil.copy(src, staged)
    rel = staged.relative_to(config.WORKSPACE)
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    data = json.dumps({"file_name": file_name or src.name, "parent_type": "bitable_image",
                       "parent_node": config.BASE_TOKEN, "size": src.stat().st_size}, ensure_ascii=False)
    try:
        r = subprocess.run(["lark-cli", "api", "POST", "/open-apis/drive/v1/medias/upload_all",
                            "--data", data, "--file", f"file={rel}", "--as", "bot"],
                           capture_output=True, text=True, cwd=str(config.WORKSPACE), env=env, timeout=120)
        out = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else ""
        d = json.loads(out) if out else {}
        if d.get("code") == 0:
            return d["data"]["file_token"]
        raise FeishuIOError(f"上传媒体失败: {str(d)[:200] or r.stderr[:200]}")
    finally:
        staged.unlink(missing_ok=True)


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


def search_records(table_name: str, conditions: list[dict], conjunction: str = "and",
                   page_size: int = 100) -> list[dict]:
    """服务端过滤查询(飞书 records/search API):按字段条件**下推**,只拉命中行(不全表拉)。
    conditions=[{"field_name":.., "operator":"is"/"isNot"/"isEmpty"/.., "value":[...]}];conjunction="and"/"or"。
    返回 record 列表,形态经 bitable 收窄 seam(text/link_record_ids/parse_ts)与 list_records **等价**
    (search 返回字段是富文本数组,bitable.text 已归一化;调用点一律走 bitable seam,不裸取字段)。
    **空 conditions → 退化 list_records(全表)**,语义不变。"""
    if not conditions:
        return list_records(table_name, page_size)
    tid = config.tables()[table_name]
    body = {"filter": {"conjunction": conjunction, "conditions": conditions}}
    items, token = [], None
    while True:
        params = {"page_size": page_size}
        if token:
            params["page_token"] = token
        d = _call("POST", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/search",
                  params, body)
        items += d.get("items") or []
        if not d.get("has_more"):
            return items
        token = d.get("page_token")


_SEARCH_COND_CHUNK = 45   # 飞书 filter conditions 有上限(~50),分块防超限


def search_in(table_name: str, field_name: str, values, page_size: int = 100) -> list[dict]:
    """便捷:『field ∈ values』服务端过滤(飞书 is 单选只收单值 → 每值一条件、conjunction=or 合并)。
    真跑验证与 list_records+内存筛等价。**空 values → 返回 []**(∈空集=无命中,不退化全表)。
    values 很多时**分块**(每块≤45,防超飞书 filter 条件上限);块间结果合并(每行只匹配一个值,不重)。"""
    vals = [v for v in (values or []) if v]
    if not vals:
        return []
    out: list[dict] = []
    for i in range(0, len(vals), _SEARCH_COND_CHUNK):
        conds = [{"field_name": field_name, "operator": "is", "value": [v]}
                 for v in vals[i:i + _SEARCH_COND_CHUNK]]
        out += search_records(table_name, conds, conjunction="or", page_size=page_size)
    return out


def name_map(table_name: str, name_field: str) -> dict[str, str]:
    """{record_id: 该行显示名} 映射(小表 账号表/内容类型表 用)。
    **为什么需要**:records/search 返回 link 字段只给 id 不给 text(与 list_records/get_record 形态不同),
    所以从 search 结果显示/匹配『账号名/内容类型名』必须靠这个把 id 还原成名(dogfood 实测:不还原→全空)。
    小表(≤数十行)一次全拉,可接受。"""
    from . import bitable
    return {r["record_id"]: bitable.text(r["fields"].get(name_field)) for r in list_records(table_name)}


def get_record(table_name: str, record_id: str) -> dict | None:
    """按 record_id 取**单条**(GET,不全表扫)。找不到→None。用于 approve/成片索引等按 id 取的场景。"""
    tid = config.tables()[table_name]
    try:
        d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{record_id}")
        return d.get("record")
    except FeishuIOError:
        return None


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
            table: str, detail: str = "", cost: float | None = None) -> None:
    """写运行日志表。日志失败只打印不阻断主流程。
    cost 给定则写结构化 成本_元 数值字段(M3);月成本核算优先读它,弃脆弱的 detail 解析。

    **table 必填,没有默认值**(2026-07-14 全体系对齐审查):原来它默认 `"笔记表"`,而 9 个调用点
    **一个都没传** → 全部静默落进默认值。于是日志里写着:
        动作=自动打标  摘要=自动打标入库 1 条 · /巧荷素材/待入库  **涉及表=笔记表**  ← 假的,是素材表
        动作=找热点    摘要=找热点落灵感库 N 条                **涉及表=笔记表**  ← 假的,是灵感库
    **出事时排障,日志会告诉你"打标在操作笔记表"——它在撒谎。**
    默认值就是陷阱:它把"忘了传"变成"静默记错"。去掉默认值,调用点必须说清自己在动哪张表。
    """
    try:
        fields = {
            RLF.SUMMARY: summary,
            RLF.TIME: int(datetime.now().timestamp() * 1000),
            RLF.EXECUTOR: "orchestrator",
            RLF.SKILL: skill,
            RLF.ACTION: action,
            RLF.TABLE_REF: table,
            RLF.RECORD_REF: note_ref,
            RLF.RESULT: result,
            RLF.DETAIL: detail[:800],
        }
        if cost is not None:
            fields[RLF.COST] = cost
        create_record("运行日志表", fields)
    except Exception as e:  # noqa: BLE001
        print(f"[log_run 降级] {e}")
