#!/usr/bin/env python3
"""素材摄入(用户场景:一堆网盘乱素材→智能体理解归类→软链上墙→登记素材表)。

设计原则(呼应用户与 workspace 记忆):
- **原件不动**:原始素材留在下载/云盘位置,只软链进 素材库/{SKU}/,不搬运不复制(引用优先)。
- **智能体决定归类**:本脚本只提供安全原语(link/register),细粒度理解与命名由 agent 现场决定,不固化目录。
- **在空间中有=地址被登记**:每个软链写一行 manifest;登记素材表=让引擎/人看得到。
- **落库位置注入**:写哪个 Base/表由 workspace(.env + schema)注入,技能/脚本不硬编码。

用法(agent 通常直接调函数;命令行是薄封装):
  scan   <src_dir>                      列出待摄入文件(agent 先看)
  link   <src> <SKU> <category> [name]  软链一个文件进 素材库/{SKU}/{category}/,记 manifest
  register <SKU> <素材编号> --type ... --note ...   把一条素材登记进测试库素材表(软链路径入'链接')
categories 约定:01-原始拍摄 02-AI生成 03-成片 04-工作台(自由,agent 可细分子目录)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import feishu_io  # noqa: E402

ASSET_ROOT = Path(os.environ.get("GY_ASSET_ROOT", str(Path.home() / "素材库")))


def _manifest(sku: str) -> Path:
    return ASSET_ROOT / sku / "manifest.jsonl"


def scan(src_dir: str) -> list[dict]:
    """列出源目录文件(agent 据此理解;不判断内容,交给 agent 多模态)。"""
    src = Path(src_dir).expanduser()
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            out.append({"path": str(p), "name": p.name, "size": p.stat().st_size, "ext": p.suffix})
    return out


def link(src: str, sku: str, category: str, name: str | None = None) -> str:
    """软链 src 进 素材库/{SKU}/{category}/{name}。原件不动。返回软链路径。"""
    srcp = Path(src).expanduser().resolve()
    if not srcp.exists():
        raise FileNotFoundError(srcp)
    dst_dir = ASSET_ROOT / sku / category
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / (name or srcp.name)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(srcp)  # 引用,不复制
    _manifest(sku).parent.mkdir(parents=True, exist_ok=True)
    with open(_manifest(sku), "a", encoding="utf-8") as f:
        f.write(json.dumps({"role": "material", "src": str(srcp), "link": str(dst),
                            "category": category, "by": "ingest"}, ensure_ascii=False) + "\n")
    return str(dst)


def _clothes_map() -> dict:
    """衣服编号→record_id(挂 SKU 用)。"""
    m = {}
    for c in feishu_io.list_records("衣服总表"):
        code = c["fields"].get("衣服编号")
        if isinstance(code, list):
            code = "".join(x.get("text", "") for x in code if isinstance(x, dict))
        if code:
            m[str(code)] = c["record_id"]
    return m


def register(sku: str, code: str, mtype: str, link_path: str, note: str = "",
             source: str = "实拍", link_sku: str | None = None, accounts: list | None = None) -> str:
    """登记素材进测试库素材表 + **挂 SKU**(解决'素材没跟SKU挂钩乱')。
    link_sku=衣服编号(如 GY-001);挂不上(SKU 不存在)则留孤儿并在返回打标。"""
    fields = {
        "素材编号": code,
        "类型": mtype,
        "链接": {"link": f"file://{link_path}", "text": Path(link_path).name},
        "拍摄状态": "已拍",
        "来源": source,
        "备注": note,
    }
    target = link_sku or sku
    cmap = _clothes_map()
    if target in cmap:
        fields["关联衣服"] = [cmap[target]]  # 摄入即挂 SKU,不再是孤儿
    if accounts:
        fields["适用账号"] = accounts
    return feishu_io.create_record("素材表", fields)


def orphans() -> list[dict]:
    """列出未挂钩素材(无关联衣服也无关联面料工艺),供 agent 补挂 SKU(存量清理)。"""
    def _t(v):
        return ",".join(x.get("text", "") for x in v if isinstance(x, dict)) if isinstance(v, list) else str(v or "")
    out = []
    for m in feishu_io.list_records("素材表"):
        f = m["fields"]
        if not _t(f.get("关联衣服")).strip() and not _t(f.get("关联面料·工艺")).strip():
            out.append({"record_id": m["record_id"], "素材编号": _t(f.get("素材编号")),
                        "类型": f.get("类型"), "备注": _t(f.get("备注"))})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("src_dir")
    l = sub.add_parser("link"); l.add_argument("src"); l.add_argument("sku")
    l.add_argument("category"); l.add_argument("name", nargs="?")
    sub.add_parser("orphans")
    r = sub.add_parser("register"); r.add_argument("sku"); r.add_argument("code")
    r.add_argument("--type", required=True); r.add_argument("--link", required=True)
    r.add_argument("--note", default=""); r.add_argument("--source", default="实拍")
    r.add_argument("--sku-link", dest="sku_link", default=None)
    a = ap.parse_args()
    if a.cmd == "scan":
        files = scan(a.src_dir)
        print(json.dumps(files, ensure_ascii=False, indent=1))
        print(f"# {len(files)} 个文件待 agent 理解归类", file=sys.stderr)
    elif a.cmd == "link":
        print(link(a.src, a.sku, a.category, a.name))
    elif a.cmd == "register":
        print(register(a.sku, a.code, a.__dict__["type"], a.link, a.note, a.source, a.sku_link))
    elif a.cmd == "orphans":
        import json as _j; print(_j.dumps(orphans(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
