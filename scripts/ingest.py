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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import feishu_io, netpan  # noqa: E402
from orchestrator.bitable import MaterialFields as MF  # noqa: E402
from orchestrator.bitable import MaterialSource as MSrc  # noqa: E402
from orchestrator.bitable import MaterialStatus as MS  # noqa: E402

ASSET_ROOT = Path(os.environ.get("GY_ASSET_ROOT", str(Path.home() / "素材库")))


def _as_pointer(link_path: str) -> str:
    """素材『链接』值(ADR-0004):已是指针/URL(baidupan:/http(s)/file:)原样;裸本地路径→file://(向后兼容本地样片)。
    网盘素材传 netpan.pointer(远端路径)=耐久指针;分享链接用时再 mint,不入库。"""
    if "://" in link_path or link_path.startswith(netpan.POINTER_SCHEME):
        return link_path
    return f"file://{link_path}"


def _resolve_link(link_path: str) -> str:
    """素材『链接』**存能点开的值**:网盘指针(real 模式)→ mint 永久分享链接(投手一点直达该图/视频);
    本地/stub → 退化成指针/file://。失败兜底存指针(不丢)。"""
    if link_path.startswith(netpan.POINTER_SCHEME) and netpan.MODE == "real":
        try:
            return netpan.share_link(netpan.pointer_path(link_path))   # 永久分享(share set --period 0)
        except netpan.NetpanError:
            return link_path
    return _as_pointer(link_path)


_TYPE_PREFIX = {"上身图": "ST", "上身视频": "SV", "形象图": "XX"}


def _batch_date(name: str) -> str:
    """从文件名抽拍摄批次日期 YYMMDD(如 '2026-07-02 175646.heic'→'260702');抽不到用 000000。"""
    m = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})", name)
    return f"{m.group(1)[2:]}{m.group(2)}{m.group(3)}" if m else "000000"


def gen_code(mtype: str, name: str, existing: set) -> str:
    """系统化素材编号 <类型>-<批次日期>-<序号>(如 ST-260702-001)。科学、可排序、不混。
    existing=已用编号集合,同(类型,批次)取最大序号+1;调用方每登记一个把返回值加进 existing。"""
    pre = _TYPE_PREFIX.get(mtype, "XX")
    date = _batch_date(name)
    stem = f"{pre}-{date}-"
    nums = [int(m.group(1)) for c in existing if (m := re.match(rf"^{pre}-{date}-(\d+)$", c))]
    return f"{stem}{(max(nums) + 1 if nums else 1):03d}"


def segment_note(parent_code: str, in_ts: str, out_ts: str, extra: str = "") -> str:
    """段指针素材的『备注』(ADR-0004 §4:用某段不物化新文件,记原片+区间,来源继承原片)。
    例:『段 00:12-00:27 源自 M-013』。人/agent 一看就知道用哪段。"""
    seg = f"段 {in_ts}-{out_ts} 源自 {parent_code}"
    return f"{seg};{extra}" if extra else seg


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
        MF.LINK: {"link": _resolve_link(link_path), "text": Path(netpan.pointer_path(link_path)).name},
        MF.SHOT_STATUS: MS.SHOT,
        MF.SOURCE: source,
        MF.NOTE: note,
    }
    if accounts:
        fields[MF.ACCOUNTS] = accounts   # 适用账号=赛道投影(薄执行器按此+类型筛选)
    return feishu_io.create_record("素材表", fields)


def store_produced(local_path: str, mtype: str, source: str = MSrc.AI, note: str = "",
                   accounts: list | None = None, remote_dir: str | None = None) -> tuple[str, str]:
    """AI/剪辑产出的成片**回传网盘 03-成片** + 登记素材(#40 ①,ADR-0004)。
    **来源随像素出处**:纯剪辑实拍=`实拍`(免声明)、含AI合成=`AI生成`(需声明)——调用方按事实传 source。
    需 netpan real+STOKEN(写)。返回 (record_id, 网盘耐久指针)。"""
    remote = remote_dir or f"{netpan.ROOT}/03-成片"
    remote_path = netpan.upload(local_path, remote)   # 真上传(写,需 STOKEN)
    ptr = netpan.pointer(remote_path)
    rid = register(Path(local_path).stem, mtype, ptr, note, source, accounts)
    return rid, ptr


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
