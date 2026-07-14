"""周报(Observation · 人面):**摆事实,不下结论。**

★这里没有"本周最有效是 X,可加权多产这类"★

老实现会自己排序、自己设阈值(`total_posts < 3` 才准下结论)、自己写出那句推荐。
**那是判断** —— 全景图的 AGENT 框里白纸黑字写着「**周报该怎么说**」是模型的事。
而且它真的编过:只有 1 条、均赞 0.0,它照样写「👉 本周最有效:『视频唯美OOTD』—— 可加权/多产这类」。
老板看了会说:就一条,还 0 赞,你让我多产?

现在:
  · **harness 摆事实**(每套方法论各几条、总赞、均赞;已发的有没有链接;有没有外部参考)
  · **agent 自己看完事实,自己说话**(`report --say "<你的结论>"`)—— 说什么、敢不敢下结论,是它的判断
  · 没数据 → 事实就是"没数据"。**它可以说"给不出结论"** —— 而那句话由它说,不是我替它说。
"""
from __future__ import annotations

from . import bitable, feishu_io, metrics
from .bitable import NoteFields as NF, NoteStatus as NS


def facts(brand: str = "巧荷") -> dict:
    """**这周的事实**(纯读,不下结论)。agent 看它,自己判断该跟老板说什么。"""
    notes = [r["fields"] for r in feishu_io.list_records(NF.TABLE)]
    # ★『外部参考』不是我们发的 → 一律排除★
    # 否则一条别人的爆款进来,任何"最佳/最有效"都会指着它 —— 数字是真的,话是假的。
    external = [f for f in notes if bitable.text(f.get(NF.OWNERSHIP)).strip() == "外部参考"]
    ours = [f for f in notes if bitable.text(f.get(NF.OWNERSHIP)).strip() != "外部参考"]
    posted = [f for f in ours if bitable.text(f.get(NF.STATUS)) in (NS.PUBLISHED, NS.LOOPED_BACK)]
    return {
        "本号已发/已回流": len(posted),
        "其中没填发布链接的": [bitable.text(f.get(NF.TITLE)) for f in posted
                               if not bitable.text(f.get(NF.PUBLISH_LINK)).strip()],
        "每套方法论": metrics.by_playbook(ours),   # {方法论: {条数, 总赞, 均赞, 总藏, 总评}}
        "外部参考(不是我们发的,不计入任何结论)": len(external),
        "提醒": "**没数据就是没数据。** 给不给结论、敢不敢给,是你的判断 —— 但别用零数据编。",
    }


def card(facts_: dict, say: str = "", needs: list[dict] | None = None) -> dict:
    """周报卡片(老板看的)。**`say` 是 agent 说的话** —— harness 一个结论都不写。"""
    el: list[dict] = []
    if say:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": say}})
    lines = [f"· 本号已发/已回流:**{facts_['本号已发/已回流']}** 条"]
    for pb, d in (facts_.get("每套方法论") or {}).items():
        lines.append(f"· 『{pb}』:{d['条数']} 条 · 总赞 {d['总赞']} · 均赞 {d['均赞']}")
    if facts_.get("其中没填发布链接的"):
        lines.append(f"· ⚠️ {len(facts_['其中没填发布链接的'])} 条已发**没填发布链接** → "
                     f"不填,互动数就采不回来")
    if facts_.get("外部参考(不是我们发的,不计入任何结论)"):
        lines.append(f"· （另有 {facts_['外部参考(不是我们发的,不计入任何结论)']} 条**外部参考**笔记在库里"
                     f"——那不是我们发的，只用来验证回流链路，**不计入上面任何数字**）")
    el.append({"tag": "div", "text": {"tag": "lark_md", "content": "**数据**\n" + "\n".join(lines)}})
    if needs:
        el.append({"tag": "hr"})
        el.append({"tag": "div", "text": {"tag": "lark_md", "content":
                   "**📷 卡在素材上的**\n" + "\n".join(
                       f"· {n.get('account', '?')}｜{n.get('类型', '?')} 缺 {n.get('缺', '?')} 条"
                       for n in needs)}})
    return {"config": {"wide_screen_mode": True},
            "header": {"template": "blue",
                       "title": {"tag": "plain_text", "content": "📊 巧荷 · 本周复盘"}},
            "elements": el}
