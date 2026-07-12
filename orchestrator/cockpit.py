"""今日驾驶舱(顺手:人/接手 agent 一条命令看完今日,不用挨个敲 run_day/publish_ready/shot_list)。

聚合人只管头尾要看的四件事(纯读,不写库、不触 LLM):
- 待审:草稿待发的笔记(你点批准)
- 待发:待发布的笔记 + 每条『用哪张素材+可开链接』(你手机发)
- 待回填链接:已发但还没贴发布链接的(不贴回流采集抓不到数据)
- 要补拍:库存见底的拍摄需求(你按需拍)
"""
from __future__ import annotations

from . import bitable, config, feishu_io, publish, shotlist
from .bitable import NoteFields as NF, NoteStatus as NS


def _note_link(record_id: str) -> str:
    """这条笔记在 base 里的深链(飞书聊天里一点直达该行去审/改)——『引导到 base 操作』。"""
    try:
        return config.record_url(NF.TABLE, record_id)
    except Exception:  # noqa: BLE001  schema 缺表名等 → 不给链接也不炸
        return ""


def today_panel(brand: str = "巧荷") -> dict:
    """今日面板:一次读全笔记表+素材,分出 待审/待发/待回填链接/要补拍。纯读。
    每条笔记带 base 深链(飞书里一点直达该行操作)——面向『聊天优先、引导到 base』。"""
    idx = publish._material_index()
    pend_review: list[dict] = []
    to_publish: list[dict] = []
    need_link: list[dict] = []
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        title = bitable.text(f.get(NF.TITLE))
        acc = bitable.text(f.get(NF.ACCOUNT))
        link = _note_link(r["record_id"])
        if st == NS.DRAFT_PENDING:
            pend_review.append({"title": title, "account": acc, "open": link})
        elif st == NS.TO_PUBLISH:
            mats = publish.note_materials(f, idx)
            to_publish.append({"title": title, "account": acc, "open": link,
                               "materials": [{"code": m["code"], "link": m["取用链接"]} for m in mats]})
        elif st == NS.PUBLISHED and not bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            need_link.append({"title": title, "account": acc, "open": link})
    return {"待审": pend_review, "待发": to_publish,
            "待回填链接": need_link, "要补拍": shotlist.shot_needs(brand)}


def _md_note(n: dict) -> str:
    """一条笔记 → lark_md 行:标题带 base 深链(可点直达该行操作),附账号。"""
    title = n["title"] or "(无标题)"
    head = f"[{title}]({n['open']})" if n.get("open") else title
    return f"· {head} · {n['account']}"


def today_card(brand: str = "巧荷", panel: dict | None = None) -> dict:
    """今日面板 → 飞书交互卡片(lark_md 正文 + 可点 base 深链)。纯函数(panel 可注入直测)。
    ADR-0005:批准/发这类点一下的动作,上线走卡片按钮回调(需服务器);现阶段深链『引导到 base』。"""
    p = panel if panel is not None else today_panel(brand)
    el: list[dict] = []

    def sec(md: str) -> None:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": md}})

    review = "\n".join(_md_note(n) for n in p["待审"]) or "· 无"
    sec(f"**📋 待你审 {len(p['待审'])} 条**（点标题去 base 批准）\n{review}")
    el.append({"tag": "hr"})
    pub_lines = []
    for n in p["待发"]:
        pub_lines.append(_md_note(n))
        for m in n["materials"]:
            pub_lines.append(f"    取素材 {m['code']}：{m['link'] or '(无链接)'}")
    sec(f"**📤 待你发 {len(p['待发'])} 条**（发完把链接发我认领，或去 base 回填）\n" + ("\n".join(pub_lines) or "· 无"))
    if p["待回填链接"]:
        el.append({"tag": "hr"})
        sec(f"**🔗 已发待回填链接 {len(p['待回填链接'])} 条**（不填回流没数据）\n"
            + "\n".join(_md_note(n) for n in p["待回填链接"]))
    el.append({"tag": "hr"})
    shoot = "\n".join(f"· {s['account']}｜{s['类型']}：缺 {s['缺']} 条" for s in p["要补拍"]) or "· 库存都够"
    sec(f"**📷 要补拍 {len(p['要补拍'])} 项**（拍完丢网盘待入库箱）\n{shoot}")

    return {"config": {"wide_screen_mode": True},
            "header": {"template": "wathet",
                       "title": {"tag": "plain_text", "content": f"📮 {brand} · 今日面板（{config.ENV_NAME}）"}},
            "elements": el}
