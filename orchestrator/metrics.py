"""效果采集 + 反馈(G7)。从已发笔记的公开页取互动数据写回笔记表,并按 playbook 聚合成
"哪套方法论有效"的反馈信号,喂回排产(闭环学习的最后一环)。

采集走 lib/xhs_fetch 统一取数口(内部链 xhs-extract-master 非登录 SSR / apify / redfox,
**零封号不用我方账号**)。默认 stub 零成本;`mode="real"` 才真取(只读安全)。
"""
from __future__ import annotations

from . import bitable
from .bitable import NoteFields as NF

# xhs_fetch 的 metrics 键 → 笔记表数值字段(热度分是 formula,Bitable 自算,不写)
_METRIC_MAP = {"liked": NF.LIKED, "collected": NF.COLLECTED, "comments": NF.COMMENTS, "shared": NF.SHARED}


def collect(url: str, mode: str = "stub") -> dict:
    """取一条已发笔记的互动数据 → {笔记表数值字段: 值}。
    mode=stub 返 {}(零成本占位);real 走 xhs_fetch(非登录零封号)。无 url / 取数失败 → {} 不阻断。"""
    if not url or mode != "real":
        return {}
    try:
        from lib import xhs_fetch
        m = (xhs_fetch.note(url) or {}).get("metrics") or {}
    except Exception as e:  # noqa: BLE001  取数失败不拦主流程,下轮重试
        print(f"[效果采集降级] {e}")
        return {}
    out = {}
    for k, field in _METRIC_MAP.items():
        v = m.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[field] = int(v)
    return out


def aggregate_by_playbook(notes: list[dict]) -> dict:
    """把已发笔记按所属 playbook 聚合互动数据 → {playbook: {条数, 总赞, 均赞, 总藏, 总评}}。
    这是反馈信号:哪套方法论平均表现好 → 排产可据此调权重(纯函数,喂 planner/复盘)。"""
    agg: dict[str, dict] = {}
    for f in notes:
        pb = bitable.text(f.get(NF.PLAYBOOK)).strip()
        if not pb:
            continue
        liked = _num(f.get(NF.LIKED))
        d = agg.setdefault(pb, {"条数": 0, "总赞": 0, "总藏": 0, "总评": 0})
        d["条数"] += 1
        d["总赞"] += liked
        d["总藏"] += _num(f.get(NF.COLLECTED))
        d["总评"] += _num(f.get(NF.COMMENTS))
    for d in agg.values():
        d["均赞"] = round(d["总赞"] / d["条数"], 1) if d["条数"] else 0
    return agg


def _num(v) -> int:
    try:
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    except (ValueError, TypeError):
        return 0
