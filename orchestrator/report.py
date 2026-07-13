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
    # **零赞的真实原因,得看真实状态**(2026-07-14 人眼审:周报让人"去回填链接",
    # 可那条已发的稿**链接早就填了** —— 它在教人做一件已经做完的事。**建议没基于真实状态 = 话在骗人**)。
    # 三种情况完全不同,别混成一句:
    #   · 已发但**没链接**      → 真该去 base 填链接
    #   · 已发**有链接**却零赞  → 链接有了,是**回流没采到**(回流还没跑真采 / 链接无效 / 登录态过期)
    #   · 压根没发过           → 无从谈起
    no_link = [f for f in posted if not bitable.text(f.get(NF.PUBLISH_LINK)).strip()]
    with_link = [f for f in posted if bitable.text(f.get(NF.PUBLISH_LINK)).strip()]
    return {
        "by_playbook": agg,
        "ranked": [{"playbook": k, **v} for k, v in ranked],
        "top": ({"title": bitable.text(top.get(NF.TITLE)), "liked": metrics._num(top.get(NF.LIKED)),
                 "playbook": bitable.text(top.get(NF.PLAYBOOK))} if top else None),
        "shot_needs": needs or [],
        "已发_无链接": len(no_link),      # 这些才是"该去回填链接"的
        "已发_有链接": len(with_link),    # 这些链接有了;零赞是回流没采到,不是没填链接
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
        # **数据不够就别下结论**(2026-07-14 走运营流程发现):真跑出的周报写着
        #   「👉 本周最有效:『视频唯美OOTD』——可加权/多产这类」
        #   「🏆 单条最佳:「OOTD｜栀子入素」赞 0」
        # ——**只有 1 条,均赞 0.0**。0 赞的"最有效"、0 赞的"最佳"。运营看了会说:
        # "就一条,还 0 赞,你让我多产?" 系统在**用零数据编结论**:刚上线时回流还没数据
        # (赞数全 0),周报照样瞎推荐,运营照做就被误导。宁可说"数据不够",也不能编。
        # 判据是「**有没有任何赞数据**」,不是「本周有没有」——刚发的帖子还没进本周窗口时,
        # 历史数据仍然能支撑结论。零赞才是真的给不出结论。
        total_liked = sum(int(r.get("总赞") or 0) for r in ranked)
        total_posts = sum(int(r.get("条数") or 0) for r in ranked)
        if total_liked <= 0:
            lines.append("\n⚠️ 本周所有帖子的赞数都是 0 —— **给不出「哪类更有效」的结论**。")
            # **建议要看真实状态**(不然就是在教人做一件已经做完的事 = 话在骗人)
            n_nolink, n_link = summary.get("已发_无链接", 0), summary.get("已发_有链接", 0)
            if n_nolink:
                lines.append(f"   · {n_nolink} 条已发但**没填链接** → 去 base 把小红书链接填进『发布链接』，"
                             "系统才采得到互动数。")
            if n_link:
                lines.append(f"   · {n_link} 条**链接已经填了**，却还是零赞 → 不是没填链接，"
                             "是**回流没采到**：回流默认 stub（不真采），要真拿数据得 `GY_METRICS_MODE=real`；"
                             "已经 real 还采不到，多半是链接无效或登录态过期（collect_metrics 会告警）。"
                             "（也可能真是刚发、还没人赞）")
        elif total_posts < 3:
            lines.append(f"\n⚠️ 本周只有 {total_posts} 条有数据 —— **样本太小，先别据此调整策略**，"
                         "再攒几条看趋势。")
        else:
            best = ranked[0]
            lines.append(f"\n👉 本周最有效：『{best['playbook']}』——可加权/多产这类。")
    top = summary.get("top")
    if top and int(top.get("liked") or 0) > 0:      # 0 赞的"最佳"是荒谬的,别报
        lines.append(f"🏆 单条最佳：「{top['title']}」赞{top['liked']}（{top['playbook'] or '—'}）")
    if summary.get("shot_needs"):
        lines.append(f"\n📷 需补拍 {len(summary['shot_needs'])} 项：")
        for n in summary["shot_needs"][:6]:
            lines.append(f"  · {n['account']}｜{n['类型']} 缺{n['缺']}条")
    return "\n".join(lines)
