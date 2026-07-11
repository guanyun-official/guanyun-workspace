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
from orchestrator.bitable import MaterialFields as MF  # noqa: E402
from orchestrator.bitable import MaterialSource as MSrc  # noqa: E402
from orchestrator.bitable import MaterialStatus as MS  # noqa: E402

ASSET_ROOT = Path(os.environ.get("GY_ASSET_ROOT", str(Path.home() / "素材库")))


def _manifest(batch: str) -> Path:
    return ASSET_ROOT / batch / "manifest.jsonl"


def scan(src_dir: str) -> list[dict]:
    """列出源目录文件(agent 据此理解;不判断内容,交给 agent 多模态)。"""
    src = Path(src_dir).expanduser()
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            out.append({"path": str(p), "name": p.name, "size": p.stat().st_size, "ext": p.suffix})
    return out


def link(src: str, batch: str, category: str, name: str | None = None) -> str:
    """软链 src 进 素材库/{批次}/{category}/{name}(§4:存按拍摄批次,不按SKU)。原件不动。返回软链路径。"""
    srcp = Path(src).expanduser().resolve()
    if not srcp.exists():
        raise FileNotFoundError(srcp)
    dst_dir = ASSET_ROOT / batch / category
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / (name or srcp.name)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(srcp)  # 引用,不复制
    _manifest(batch).parent.mkdir(parents=True, exist_ok=True)
    with open(_manifest(batch), "a", encoding="utf-8") as f:
        f.write(json.dumps({"role": "material", "src": str(srcp), "link": str(dst),
                            "category": category, "by": "ingest"}, ensure_ascii=False) + "\n")
    return str(dst)


def register(code: str, mtype: str, link_path: str, note: str = "",
             source: str = MSrc.REAL, accounts: list | None = None) -> str:
    """登记素材进测试库素材表(§4:素材按赛道存,不挂衣服)。
    accounts=适用账号 record_id 列表(赛道=账号×模式 投影);类型(类型字段)是薄执行器选素材的 key。"""
    fields = {
        MF.CODE: code,
        MF.TYPE: mtype,
        MF.LINK: {"link": f"file://{link_path}", "text": Path(link_path).name},
        MF.SHOT_STATUS: MS.SHOT,
        MF.SOURCE: source,
        MF.NOTE: note,
    }
    if accounts:
        fields[MF.ACCOUNTS] = accounts   # 适用账号=赛道投影(薄执行器按此+类型筛选)
    return feishu_io.create_record("素材表", fields)


def orphans() -> list[dict]:
    """列出未归赛道素材(无适用账号),供 agent 补挂赛道(§4:素材按赛道不挂衣服)。"""
    from orchestrator import bitable
    _t = bitable.text
    out = []
    for m in feishu_io.list_records("素材表"):
        f = m["fields"]
        if not _t(f.get(MF.ACCOUNTS)).strip():
            out.append({"record_id": m["record_id"], "素材编号": _t(f.get(MF.CODE)),
                        "类型": f.get(MF.TYPE), "备注": _t(f.get(MF.NOTE))})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("src_dir")
    l = sub.add_parser("link"); l.add_argument("src"); l.add_argument("batch")
    l.add_argument("category"); l.add_argument("name", nargs="?")
    sub.add_parser("orphans")
    r = sub.add_parser("register"); r.add_argument("code")
    r.add_argument("--type", required=True); r.add_argument("--link", required=True)
    r.add_argument("--note", default=""); r.add_argument("--source", default="实拍")
    r.add_argument("--accounts", default="", help="适用账号 record_id 逗号分隔(赛道投影)")
    # 大刀阔斧:子素材视图(select/view/summary/trace,依赖 lib/material_view)已砍——过早精致,见交接文档 §5。
    # 保留的是安全摄入原语 scan/link/register/orphans(原件不动、软链上墙、登记素材表)。
    a = ap.parse_args()
    if a.cmd == "scan":
        files = scan(a.src_dir)
        print(json.dumps(files, ensure_ascii=False, indent=1))
        print(f"# {len(files)} 个文件待 agent 理解归类", file=sys.stderr)
    elif a.cmd == "link":
        print(link(a.src, a.batch, a.category, a.name))
    elif a.cmd == "register":
        accs = [x for x in a.accounts.split(",") if x]
        print(register(a.code, a.__dict__["type"], a.link, a.note, a.source, accs or None))
    elif a.cmd == "orphans":
        import json as _j; print(_j.dumps(orphans(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
