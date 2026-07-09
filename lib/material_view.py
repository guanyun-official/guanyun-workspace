"""素材视图层 + 使用账本(盘上机器索引)。见 docs/架构演进-素材视图与方法论.md · G8。

核心结构(每账号的每套发布方法论 playbook 一套视图 = 一个"bin"稳定精选池):
- **子素材 clip**:原始文件的一个切片/切面。稳定标识 `clip_id = 哈希(素材编号, span)`——
  键于 ingest 分配的**稳定文件ID(素材编号)+ span 描述**,不含路径/内容哈希:原始文件搬家、
  重编码,clip_id 不变(`relink` 只改 src 指针)。这是子素材可回溯的地基。
- **视图 manifest** `_views/{账号}/{playbook}.jsonl`:该 playbook 选进 bin 的子素材(选择,非拼装)。
- **使用账本** `_usage.jsonl`:笔记发布后回填"哪条笔记用了哪个 clip、用了多少"——**usage 唯一真值**
  (盘权威;Bitable 只做只写投影,见设计文档第四节)。linked(选入范围)vs used(实际用掉范围)
  两个量,类比剪辑软件的"选中 vs 用上"。

纯盘 + stdlib,零网络零 Base。时间戳由调用方传入(determinism:模块内不取 now)。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ASSET_ROOT = Path(os.environ.get("GY_ASSET_ROOT", str(Path.home() / "素材库")))


def clip_id(material_code: str, span: str) -> str:
    """稳定子素材 ID = 确定性哈希(素材编号, span)。不含路径/内容哈希——文件搬家/重编码不断链。"""
    h = hashlib.sha1(f"{material_code}\x1f{span}".encode("utf-8")).hexdigest()[:12]
    return f"clip_{h}"


def pct(part: float, total: float) -> float:
    """占比(%),total<=0 时返 0 不炸。linked%/used% 都走它。"""
    return round(100.0 * part / total, 1) if total and total > 0 else 0.0


def _view_path(account: str, playbook: str, root: Path) -> Path:
    return root / "_views" / account / f"{playbook}.jsonl"


def _usage_path(root: Path) -> Path:
    return root / "_usage.jsonl"


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def add_select(account: str, playbook: str, material_code: str, src: str, span: str,
               dims: dict | None = None, linked: float | None = None,
               root: Path = ASSET_ROOT) -> str:
    """把一个子素材选进某账号某 playbook 的视图(bin)。返回 clip_id。
    幂等:同 clip_id 覆盖(重复选同一切片不产生重复行)。dims=AI 维护的语义维度(人不必读)。"""
    cid = clip_id(material_code, span)
    rec = {"clip_id": cid, "material": material_code, "src": src, "span": span,
           "dims": dims or {}, "linked": linked}
    p = _view_path(account, playbook, root)
    rows = [r for r in _read_jsonl(p) if r.get("clip_id") != cid]
    rows.append(rec)
    _write_jsonl(p, rows)
    return cid


def view_selects(account: str, playbook: str, root: Path = ASSET_ROOT) -> list[dict]:
    """某账号某 playbook 视图里的全部子素材选择。"""
    return _read_jsonl(_view_path(account, playbook, root))


def relink(material_code: str, new_src: str, root: Path = ASSET_ROOT) -> int:
    """原始文件搬家:把所有视图里该素材的 src 指到新位置,clip_id **不变**。返回改了几条。
    类比 Premiere "Locate Media"——地址变了、身份不变。"""
    changed = 0
    views_dir = root / "_views"
    if not views_dir.exists():
        return 0
    for p in views_dir.rglob("*.jsonl"):
        rows = _read_jsonl(p)
        hit = False
        for r in rows:
            if r.get("material") == material_code and r.get("src") != new_src:
                r["src"] = new_src
                hit = True
                changed += 1
        if hit:
            _write_jsonl(p, rows)
    return changed


def record_usage(clip: str, note: str, playbook: str, used: float | None = None,
                 ts: int | None = None, root: Path = ASSET_ROOT) -> None:
    """记一条使用(笔记发布后回填)。append-only,usage.jsonl = 使用唯一真值。
    ts 由调用方传入(模块内不取 now,保 determinism)。"""
    p = _usage_path(root)
    rows = _read_jsonl(p)
    rows.append({"clip_id": clip, "note": note, "playbook": playbook, "used": used, "ts": ts})
    _write_jsonl(p, rows)


def all_usage(root: Path = ASSET_ROOT) -> list[dict]:
    """整本使用账本(planner 算某账号已用哪些 clip 用)。"""
    return _read_jsonl(_usage_path(root))


def usage_of(clip: str, root: Path = ASSET_ROOT) -> list[dict]:
    """某子素材被哪些笔记用过(回溯正向:clip→笔记)。"""
    return [r for r in _read_jsonl(_usage_path(root)) if r.get("clip_id") == clip]


def note_clips(note: str, root: Path = ASSET_ROOT) -> list[str]:
    """某笔记用了哪些子素材(回溯反向:笔记→clip,支撑 G5)。"""
    return [r["clip_id"] for r in _read_jsonl(_usage_path(root)) if r.get("note") == note]


def trace_note(note: str, root: Path = ASSET_ROOT) -> list[dict]:
    """回溯一条笔记(G5):笔记 → 用了哪些 clip → 各 clip 的原始素材/切片/来源视图。
    在盘上把 usage 账本与所有视图 manifest 连起来,给人/agent 一个完整溯源。"""
    view_index: dict[str, dict] = {}
    views_dir = root / "_views"
    if views_dir.exists():
        for p in views_dir.rglob("*.jsonl"):
            # 路径形如 _views/{账号}/{playbook}.jsonl
            account, playbook = p.parent.name, p.stem
            for s in _read_jsonl(p):
                s = {**s, "account": account, "playbook": playbook}
                view_index.setdefault(s["clip_id"], s)  # 首见即锚(clip_id 稳定,不同视图同 clip 等价)
    out = []
    for u in _read_jsonl(_usage_path(root)):
        if u.get("note") != note:
            continue
        v = view_index.get(u["clip_id"], {})
        out.append({"clip_id": u["clip_id"], "used": u.get("used"),
                    "material": v.get("material"), "span": v.get("span"), "src": v.get("src"),
                    "account": v.get("account"), "playbook": v.get("playbook")})
    return out


def material_usage(material_code: str, total: float | None = None, root: Path = ASSET_ROOT) -> dict:
    """某原始素材的使用率(剪辑软件式 linked% vs used%,G3)。
    - linked = 选入各视图的切片范围总和(按 clip_id 去重,同 clip 在多视图算一次);
    - used   = 其中已被笔记用掉的切片范围总和(used ⊆ linked)。
    给了 total(如视频总时长/图总量)则同时给 linked%/used%——回答"这段素材软链了多少、用了多少"。
    每个 clip 的范围取其 select 的 `linked`(缺则按 1 计,退化为条数口径)。"""
    clips: dict[str, float] = {}
    vd = root / "_views"
    if vd.exists():
        for p in vd.rglob("*.jsonl"):
            for s in _read_jsonl(p):
                if s.get("material") == material_code:
                    lk = s.get("linked")
                    clips[s["clip_id"]] = float(lk) if lk is not None else 1.0
    used_ids = {u["clip_id"] for u in _read_jsonl(_usage_path(root)) if u.get("clip_id") in clips}
    linked = round(sum(clips.values()), 2)
    used = round(sum(v for c, v in clips.items() if c in used_ids), 2)
    out = {"material": material_code, "clips": len(clips), "used_clips": len(used_ids),
           "linked": linked, "used": used}
    if total:
        out["linked_pct"] = pct(linked, total)
        out["used_pct"] = pct(used, total)
    return out


def write_summary(account: str, playbook: str, root: Path = ASSET_ROOT) -> Path:
    """从视图 manifest 生成人可读 `.summary.md`(评审 finding#5 逃生口):每个子素材一行
    '为什么选它'(素材+切片+语义维度)。仅调试用、**非真相源**——发错料时人能回溯。返回路径。"""
    selects = view_selects(account, playbook, root)
    lines = [f"# 视图 · {account} / {playbook}", "",
             f"> 机器 manifest 的人读镜像({len(selects)} 个子素材)。非真相源,调试用。", ""]
    for s in selects:
        dims = "、".join(f"{k}={v}" for k, v in (s.get("dims") or {}).items())
        lines.append(f"- `{s['clip_id']}` ← {s.get('material')} [{s.get('span')}]"
                     + (f" · {dims}" if dims else ""))
    p = root / "_views" / account / f"{playbook}.summary.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
