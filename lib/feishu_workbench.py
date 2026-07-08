"""
feishu_workbench.py — 「飞书工位」(CONTEXT.md / ADR-0002 的落地实现)。

飞书 = 动态数据的真源;本模块是系统侧通往飞书的读写层 + 一张轻量本地幂等账本。
ADR-0002 三条铁律,全部 by construction 焊在代码里(不靠模型/人自觉):

  1) 列所有权:HUMAN_FIELDS(状态/发布时间/终稿/审核备注/可借鉴点…)是**人拥有**的列。
     写入前一律 strip 掉 → "系统永不覆盖人改过的列"是**结构性保证**。
  2) 轻量本地幂等账本:.feishu_workbench/idem-<brand>.json 记 {idem_key → record_id}。
     重跑同一 idem_key → 更新同一条(不重复落库);这张账本是"我写过什么"的唯一来源。
  3) 状态单向回流:read_status() 只读人拥有的列、且**只认账本里我们写过的 record**
     → 防回环(不碰别人/人新建的行);回流单向(系统读状态,从不回写状态)。

依赖:lark-cli(身份走 bot/璃奈,见 live-integration-env memory)。不依赖 LLM。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "lib"))

# 人拥有的列:工位绝不写(deny-list)。新增人工列只需往这里加一行。
HUMAN_FIELDS = {"状态", "发布时间", "终稿", "审核备注", "可借鉴点"}

IDEM_DIR = WORKSPACE / ".feishu_workbench"


def _load_dotenv() -> None:
    """把 WORKSPACE/.env 读进 os.environ(只填未设置的键)。密钥(如 LARK_APP_TOKEN)不入库。"""
    f = WORKSPACE / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


# ---------- lark-cli 封装(沿用已验证的调用 + 重试) ----------
def _run_lark(args: list) -> dict:
    cmd = ["lark-cli", "base"] + args
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    last = ""
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE), env=env, timeout=30)
        out = r.stdout.strip()
        last = out or (r.stderr or "").strip()
        if out:
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                raise RuntimeError(f"lark-cli 返回非 JSON: {out[:300]}")
            if not data.get("ok"):
                raise RuntimeError(f"lark-cli 失败: {data.get('error') or out[:300]}")
            return data
        if attempt < 2:
            time.sleep(2 + attempt)
    raise RuntimeError(f"lark-cli 3 次重试均返回空 (last={last[:200]})")


# ---------- 表解析 ----------
def _resolve(brand: dict, table_key: str) -> tuple[str, str]:
    """table_key → (base_token, table_id)。先查 review_tables(待审),再查 public_tables。"""
    lc = brand["lark_config"]
    base_token = os.environ.get("LARK_APP_TOKEN") or lc["base"].get("app_token", "")
    if not base_token:
        raise RuntimeError("缺飞书 base token:请在 .env 设 LARK_APP_TOKEN(见 .env.example)")
    for group in ("review_tables", "public_tables"):
        if table_key in lc.get(group, {}):
            return base_token, lc[group][table_key]["table_id"]
    raise KeyError(f"未知表 '{table_key}'（不在 review_tables / public_tables）")


# ---------- 列所有权:剥掉人拥有的列 ----------
def strip_human_fields(fields: dict) -> tuple[dict, list]:
    clean = {k: v for k, v in fields.items() if k not in HUMAN_FIELDS}
    dropped = [k for k in fields if k in HUMAN_FIELDS]
    return clean, dropped


# ---------- 本地幂等账本 ----------
def _idem_file(brand_id: str) -> Path:
    return IDEM_DIR / f"idem-{brand_id}.json"


def _load_idem(brand_id: str) -> dict:
    f = _idem_file(brand_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save_idem(brand_id: str, d: dict) -> None:
    IDEM_DIR.mkdir(exist_ok=True)
    _idem_file(brand_id).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 原子读写 ----------
def _upsert_raw(base_token: str, table_id: str, fields: dict, record_id: str | None = None) -> str:
    args = ["+record-upsert", "--base-token", base_token, "--table-id", table_id,
            "--json", json.dumps(fields, ensure_ascii=False)]
    if record_id:
        args += ["--record-id", record_id]
    data = _run_lark(args)
    d = data.get("data", {})
    rec = d.get("record", {}) if isinstance(d.get("record"), dict) else {}
    rid = ((rec.get("record_id_list") or d.get("record_id_list") or [None])[0]
           or rec.get("record_id") or d.get("record_id") or rec.get("id"))
    # 更新回包偶尔不带 id → 回落到我们传入的 record_id,保证幂等更新不丢 id
    return rid or record_id or ""


def _get_record(base_token: str, table_id: str, record_id: str) -> dict:
    data = _run_lark(["+record-get", "--base-token", base_token, "--table-id", table_id, "--record-id", record_id])
    rec = data.get("data", {}).get("record", {})
    # gotcha:字段直接挂在 data.record 下(不是 data.record.fields)
    return rec.get("fields", rec)


def _delete_raw(base_token: str, table_id: str, record_id: str) -> None:
    _run_lark(["+record-delete", "--base-token", base_token, "--table-id", table_id,
               "--record-id", record_id, "--yes"])


# ---------- 列自愈:写入即自动建缺失列 ----------
_FIELDS_CACHE: dict = {}  # (base_token, table_id) -> set(已有列名),避免批量写反复 list


def _ensure_fields(base_token: str, table_id: str, names) -> None:
    """写入前确保这些列存在,缺的自动建(text 型)。
    → "数据源新增字段"时不必再手动 field-create,表自愈(见 [[data-source-skill-alignment]])。
    新列默认 text(数值/链接列如需特定类型请预先建);已存在的列不动、类型不变。"""
    ckey = (base_token, table_id)
    existing = _FIELDS_CACHE.get(ckey)
    if existing is None:
        try:
            data = _run_lark(["+field-list", "--base-token", base_token, "--table-id", table_id])
            existing = {f.get("name") for f in data.get("data", {}).get("fields", [])}
        except RuntimeError:
            return  # 列不出来就不强建,交给后续 upsert(飞书也会对未知列报错)
        _FIELDS_CACHE[ckey] = existing
    for name in names:
        if name and name not in existing:
            try:
                _run_lark(["+field-create", "--base-token", base_token, "--table-id", table_id,
                           "--json", json.dumps({"name": name, "type": "text"}, ensure_ascii=False)])
                print(f"  ⓘ 工位自动建列: {name}", file=sys.stderr)
            except RuntimeError:
                pass  # 已存在/并发 → 当作已有
            existing.add(name)


# ---------- 对外:写 / 回流读 / 清理 ----------
def write(brand: dict, table_key: str, fields: dict, idem_key: str) -> str:
    """把系统拥有的字段写入飞书(待审/库)。幂等:同 idem_key 更新同一条。
    人拥有的列(HUMAN_FIELDS)自动剥离,绝不覆盖。缺失列自动建。返回 record_id。"""
    base_token, table_id = _resolve(brand, table_key)
    clean, dropped = strip_human_fields(fields)
    if dropped:
        print(f"  ⓘ 工位剥离人拥有的列(不写): {dropped}", file=sys.stderr)
    _ensure_fields(base_token, table_id, clean.keys())  # 列自愈:缺的自动建
    ledger = _load_idem(brand["brand_id"])
    key = f"{table_key}::{idem_key}"
    rid = _upsert_raw(base_token, table_id, clean, ledger.get(key))
    ledger[key] = rid
    _save_idem(brand["brand_id"], ledger)
    return rid


def read_status(brand: dict, table_key: str, idem_key: str, columns: list | None = None) -> dict | None:
    """单向回流:只读人拥有的列,且只认账本里我们写过的 record(防回环)。
    未写过 → None(不碰非自有行)。"""
    ledger = _load_idem(brand["brand_id"])
    rid = ledger.get(f"{table_key}::{idem_key}")
    if not rid:
        return None
    base_token, table_id = _resolve(brand, table_key)
    rec = _get_record(base_token, table_id, rid)
    cols = columns or list(HUMAN_FIELDS)
    return {"record_id": rid, **{c: rec.get(c) for c in cols if c in rec}}


def _api(method: str, path: str, params: dict | None = None, data: dict | None = None) -> dict:
    """通用 lark-cli api 调用(query 走 --params,body 走 --data)。失败返回 {}。"""
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    args = ["lark-cli", "api", method, path]
    if params:
        args += ["--params", json.dumps(params)]
    if data:
        args += ["--data", json.dumps(data)]
    out = subprocess.run(args, capture_output=True, text=True, cwd=str(WORKSPACE), env=env, timeout=30).stdout
    try:
        return json.loads(out[out.find("{"):]) if "{" in out else {}
    except json.JSONDecodeError:
        return {}


# 公开链接里"可设置"的字段(其余如 lock_switch/invite_external 只读或不照搬)
_PUBLIC_FIELDS = ("link_share_entity", "external_access", "comment_entity", "security_entity", "share_entity")


def _copy_public(doc_token: str, ref_token: str, ref_type: str) -> dict:
    """把 ref(主表/主库)的"公开链接"设置原样复制到文档 → 文档可见性 = 主表当下的可见性。
    注意:这是**建文档当下的快照**。主表之后再改可见性,已建文档不会自动跟变
    (飞书里被链接引用的独立文档,与表之间没有权限继承)。要重新对齐用 sync_doc_public()。"""
    got = _api("GET", f"/open-apis/drive/v1/permissions/{ref_token}/public", params={"type": ref_type})
    pub = (got.get("data") or {}).get("permission_public") or {}
    body = {k: pub[k] for k in _PUBLIC_FIELDS if k in pub}
    if body:
        _api("PATCH", f"/open-apis/drive/v1/permissions/{doc_token}/public", params={"type": "docx"}, data=body)
    return body


def sync_doc_public(doc_token: str, ref_token: str, ref_type: str) -> dict:
    """主表可见性改了之后,把某文档重新对齐到主表当下的设置(对外可调用)。"""
    return _copy_public(doc_token, ref_token, ref_type)


def create_doc(title: str, markdown: str) -> dict:
    """建飞书文档(lark-cli docs +create, v2);markdown 走 stdin。返回 {url, token}。
    长文/矩阵关系层等富内容用此——文档链接回填多维表 cell(doc-link 模式),保持表格可读。
    若 .env 设了 LARK_DOC_PUBLIC_REF=<token>:<type>,建好即把该主表的公开设置复制到文档
    → 文档可见性与主表一致(任何人可看/可编辑等,照搬主表)。"""
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    proc = subprocess.run(
        ["lark-cli", "docs", "+create", "--title", title, "--markdown", "-"],
        input=markdown, capture_output=True, text=True, cwd=str(WORKSPACE), env=env, timeout=60)
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"建文档失败: {(proc.stderr or out)[:300]}")
    data = json.loads(out)
    if not data.get("ok"):
        raise RuntimeError(f"建文档失败: {data.get('error') or out[:200]}")
    d = data.get("data", {})
    token = d.get("doc_id") or d.get("document_id") or d.get("token", "")
    url = d.get("doc_url") or d.get("url") or (f"https://www.feishu.cn/docx/{token}" if token else "")
    ref = os.environ.get("LARK_DOC_PUBLIC_REF", "").strip()
    if token and ref and ":" in ref:
        ref_token, ref_type = ref.rsplit(":", 1)
        try:
            _copy_public(token, ref_token, ref_type)
        except Exception as e:  # 设可见性失败不阻断落库(文档已建好)
            print(f"  ⚠ 文档对齐主表可见性失败: {e}", file=sys.stderr)
    return {"url": url, "token": token, "raw": d}


def add_diagram(doc_id: str, mermaid: str) -> str:
    """给已含 <whiteboard type="blank"/> 的文档,把 mermaid 灌进那个画板(飞书原生·可编辑)。
    返回画板 token。文档需先用 create_doc(markdown 里带 <whiteboard type="blank"/>) 建出空白画板。"""
    env = os.environ.copy()
    env["LARK_CLI_NO_PROXY"] = "1"
    fetched = subprocess.run(["lark-cli", "docs", "+fetch", "--doc", doc_id],
                             capture_output=True, text=True, cwd=str(WORKSPACE), env=env, timeout=60).stdout
    m = re.search(r'whiteboard[^>]*token=\\?"?([A-Za-z0-9]{16,})', fetched)
    if not m:
        raise RuntimeError("文档里没有空白画板块(create_doc 的 markdown 需含 <whiteboard type=\"blank\"/>)")
    wt = m.group(1)
    proc = subprocess.run(
        ["lark-cli", "docs", "+whiteboard-update", "--whiteboard-token", wt,
         "--input_format", "mermaid", "--source", "-", "--overwrite", "--yes"],
        input=mermaid, capture_output=True, text=True, cwd=str(WORKSPACE), env=env, timeout=60)
    out = proc.stdout.strip()
    data = json.loads(out[out.find("{"):]) if "{" in out else {}
    if not data.get("ok"):
        raise RuntimeError(f"灌画板失败: {(proc.stderr or out)[:200]}")
    return wt


def forget(brand: dict, table_key: str, idem_key: str, delete_remote: bool = False) -> None:
    """从账本移除(可选连带删除飞书记录)。仅用于测试/回收。"""
    ledger = _load_idem(brand["brand_id"])
    key = f"{table_key}::{idem_key}"
    rid = ledger.pop(key, None)
    if rid and delete_remote:
        base_token, table_id = _resolve(brand, table_key)
        _delete_raw(base_token, table_id, rid)
    _save_idem(brand["brand_id"], ledger)


if __name__ == "__main__":
    import argparse
    from brand_kb import load_brand
    ap = argparse.ArgumentParser(description="飞书工位自检")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--table", default="explosive_library")
    args = ap.parse_args()
    b = load_brand(args.brand)
    bt, tid = _resolve(b, args.table)
    print(f"✓ 工位解析表 {args.table} → base={bt[:8]}… table={tid}")
    print(f"✓ 人拥有列(不写): {sorted(HUMAN_FIELDS)}")
    print(f"✓ 幂等账本: {_idem_file(args.brand)}")
