"""每周总结(人只管头尾的『尾』之后的复盘一环):读回流的效果数 → 人可读周报。

哪号/哪套方法论/哪类内容表现好(均赞/本周/周环比)+ 本周最佳 + 需补拍 → 一段人打开就懂的话。
纯计算(weekly_summary 吃 notes/needs 参数,可直测);CLI 读库 + 可推飞书。喂周复盘飞轮调技能权重。
"""
from __future__ import annotations

from datetime import datetime

from . import bitable, metrics
from .bitable import NoteFields as NF, NoteStatus as NS


def weekly_summary(notes: list[dict], needs: list[dict] | None = None,
                   now: datetime | None = None) -> dict:
    """按 playbook 聚合效果 + 排名 + 本周最佳 + 补拍需求。notes=笔记表 fields 列表,needs=拍摄需求单。"""
    agg = metrics.aggregate_by_playbook(notes, now=now)
    ranked = sorted(agg.items(), key=lambda kv: (kv[1]["本周"]["均赞"], kv[1]["均赞"]), reverse=True)
    # 本周最佳:已发/已回流里点赞最高的一条
    posted = [f for f in notes if bitable.text(f.get(NF.STATUS)) in (NS.PUBLISHED, NS.LOOPED_BACK)]
    top = max(posted, key=lambda f: metrics._num(f.get(NF.LIKED)), default=None)
    return {
        "by_playbook": agg,
        "ranked": [{"playbook": k, **v} for k, v in ranked],
        "top": ({"title": bitable.text(top.get(NF.TITLE)), "liked": metrics._num(top.get(NF.LIKED)),
                 "playbook": bitable.text(top.get(NF.PLAYBOOK))} if top else None),
        "shot_needs": needs or [],
    }


def format_weekly(summary: dict) -> str:
    """周报文本(飞书友好)。"""
    lines = ["📊 巧荷·本周复盘"]
    ranked = summary["ranked"]
    if not ranked:
        lines.append("（本周暂无已发/已回流的效果数据——先跑 collect_metrics 采集回流）")
    else:
        lines.append("\n各方法论表现（按本周均赞）：")
        for r in ranked:
            wow = r.get("周环比")
            wow_s = f" 周环比{wow:+.0f}%" if isinstance(wow, (int, float)) else ""
            lines.append(f"  · {r['playbook']}：共{r['条数']}条 均赞{r['均赞']}"
                         f"（本周{r['本周']['条数']}条·均赞{r['本周']['均赞']}{wow_s}）")
        best = ranked[0]
        lines.append(f"\n👉 本周最有效：『{best['playbook']}』——可加权/多产这类。")
    if summary.get("top"):
        t = summary["top"]
        lines.append(f"🏆 单条最佳：「{t['title']}」赞{t['liked']}（{t['playbook'] or '—'}）")
    if summary.get("shot_needs"):
        lines.append(f"\n📷 需补拍 {len(summary['shot_needs'])} 项：")
        for n in summary["shot_needs"][:6]:
            lines.append(f"  · {n['account']}｜{n['类型']} 缺{n['缺']}条")
    return "\n".join(lines)
