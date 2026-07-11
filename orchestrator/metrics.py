"""效果采集 + 反馈(G7)。从已发笔记的公开页取互动数据写回笔记表,并按 playbook 聚合成
"哪套方法论有效"的反馈信号,喂回排产(闭环学习的最后一环)。

采集走 lib/xhs_fetch 统一取数口(内部链 xhs-extract-master 非登录 SSR / apify / redfox,
**零封号不用我方账号**)。默认 stub 零成本;`mode="real"` 才真取(只读安全)。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

from . import bitable, config
from .bitable import NoteFields as NF

# xhs-extract-master note 原子的 interactInfo.* → 笔记表数值字段(热度分是 formula,Bitable 自算,不写)
_METRIC_MAP = {"likedCount": NF.LIKED, "collectedCount": NF.COLLECTED,
               "commentCount": NF.COMMENTS, "shareCount": NF.SHARED}


def _cn_num(v) -> int | None:
    """小红书中文计数 → int:'8.5万'→85000,'1.2亿'→120000000,'815'→815,'-'/''→None。"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*(万|亿)?$", s)
    if not m:
        return None
    n = float(m.group(1)) * {"万": 1e4, "亿": 1e8}.get(m.group(2), 1)
    return int(round(n))


def _extract_note(url: str) -> dict:
    """调已验证的非登录 SSR 提取技能 xhs-extract-master 的 note 原子,返回原始 note dict。
    零封号不用我方账号(实测拉到巧荷账号公开数据 tikhub/redfox 皆 ✗ 仍成功)。"""
    xhs = config.WORKSPACE / "skills" / "xhs-extract-master" / "scripts" / "xhs"
    r = subprocess.run(["python3", str(xhs), "note", url],
                       capture_output=True, text=True, timeout=90)
    i = r.stdout.find("{")
    return json.loads(r.stdout[i:]) if i >= 0 else {}


def collect(url: str, mode: str = "stub") -> dict:
    """取一条已发笔记的互动数据 → {笔记表数值字段: 值}。
    mode=stub 返 {}(零成本占位);real 走 xhs-extract-master 非登录抓取。无 url / 取数失败 → {} 不阻断。"""
    if not url or mode != "real":
        return {}
    try:
        d = _extract_note(url)
    except Exception as e:  # noqa: BLE001  取数失败不拦主流程,下轮重试
        print(f"[效果采集降级] {e}", file=sys.stderr)  # 诊断走 stderr,不污染 stdout(否则骗过测试监控 tail)
        return {}
    ii = d.get("interactInfo") or {}
    out = {}
    for k, field in _METRIC_MAP.items():
        n = _cn_num(ii.get(k))
        if n is not None:
            out[field] = n
    return out


def _window() -> dict:
    return {"条数": 0, "_总赞": 0}


def _add_window(d: dict, key: str, liked: int) -> None:
    d[key]["条数"] += 1
    d[key]["_总赞"] += liked


def _finish_window(w: dict) -> dict:
    n = w["条数"]
    return {"条数": n, "均赞": round(w["_总赞"] / n, 1) if n else 0}


def aggregate_by_playbook(notes: list[dict], now: datetime | None = None) -> dict:
    """把已发笔记按所属 playbook 聚合互动数据。

    返回总量字段 + 时间窗反馈:
    `{playbook: {条数, 总赞, 均赞, 总藏, 总评, 近30天, 本周, 上周, 周环比}}`。
    这是反馈信号:哪套方法论平均表现好/最近是否变好 → 排产与周复盘可据此调权重。
    """
    now = now or datetime.now()
    recent_cutoff = now - timedelta(days=30)
    this_week_cutoff = now - timedelta(days=7)
    prev_week_cutoff = now - timedelta(days=14)
    agg: dict[str, dict] = {}
    for f in notes:
        pb = bitable.text(f.get(NF.PLAYBOOK)).strip()
        if not pb:
            continue
        liked = _num(f.get(NF.LIKED))
        d = agg.setdefault(pb, {"条数": 0, "总赞": 0, "总藏": 0, "总评": 0,
                                "近30天": _window(), "本周": _window(), "上周": _window()})
        d["条数"] += 1
        d["总赞"] += liked
        d["总藏"] += _num(f.get(NF.COLLECTED))
        d["总评"] += _num(f.get(NF.COMMENTS))
        published_at = bitable.parse_ts(f.get(NF.PUBLISHED_AT))
        if not published_at:
            continue
        if published_at >= recent_cutoff:
            _add_window(d, "近30天", liked)
        if published_at >= this_week_cutoff:
            _add_window(d, "本周", liked)
        elif published_at >= prev_week_cutoff:
            _add_window(d, "上周", liked)
    for d in agg.values():
        d["均赞"] = round(d["总赞"] / d["条数"], 1) if d["条数"] else 0
        d["近30天"] = _finish_window(d["近30天"])
        d["本周"] = _finish_window(d["本周"])
        d["上周"] = _finish_window(d["上周"])
        prev = d["上周"]["均赞"]
        d["周环比"] = round((d["本周"]["均赞"] - prev) / prev * 100, 1) if prev else None
    return agg


def _num(v) -> int:
    """健壮取数:int/float/字符串数字/中文计数('8.5万')都吃(飞书数值字段回读常为字符串)。非数→0。"""
    n = _cn_num(v)
    return n if n is not None else 0
