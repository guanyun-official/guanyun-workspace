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
        mode = bitable.text(f.get(NF.CONTENT_TYPE))
        if st == NS.DRAFT_PENDING:
            pend_review.append({"title": title, "account": acc, "mode": mode, "open": link})
        elif st == NS.TO_PUBLISH:
            mats = publish.note_materials(f, idx)
            to_publish.append({"title": title, "account": acc, "mode": mode, "open": link,
                               "materials": [{"code": m["code"], "link": m["取用链接"]} for m in mats]})
        elif st == NS.PUBLISHED and not bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            need_link.append({"title": title, "account": acc, "mode": mode, "open": link})
    return {"待审": pend_review, "待发": to_publish,
            "待回填链接": need_link, "要补拍": shotlist.shot_needs(brand)}


def _title_link(n: dict) -> str:
    """笔记 → 可点标题(base 深链;点进去素材/文案都在,卡片不再堆细节)。"""
    t = n["title"] or "(无标题)"
    return f"[{t}]({n['open']})" if n.get("open") else t


def today_card(brand: str = "巧荷", panel: dict | None = None) -> dict:
    """今日面板 → 飞书交互卡片。**按 账号·模式 分块**,每块只列可点标题+状态图标(📋待审/📤待发/🔗回填);
    素材/文案细节点进 base 看,卡片不堆。补拍归底部按账号。纯函数(panel 可注入直测)。ADR-0005。"""
    p = panel if panel is not None else today_panel(brand)

    # 按 (账号, 模式) 归块;块内按状态给图标
    blocks: dict[tuple, list[str]] = {}
    for icon, bucket in (("📋", "待审"), ("📤", "待发"), ("🔗", "待回填链接")):
        for n in p[bucket]:
            key = (n["account"], n.get("mode", ""))
            blocks.setdefault(key, []).append(f"{icon} {_title_link(n)}")

    el: list[dict] = []
    for (acc, mode), lines in sorted(blocks.items()):
        head = f"**{acc}{' · ' + mode if mode else ''}**"
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": head + "\n" + "\n".join(lines)}})

    # 补拍:按账号归拢一行(拍完丢投递箱,细节 base 看)
    shoot: dict[str, list[str]] = {}
    for s in p["要补拍"]:
        shoot.setdefault(s["account"], []).append(f"{s['类型']}×{s['缺']}")
    if shoot:
        el.append({"tag": "hr"})
        lines = [f"· {acc}：{'、'.join(items)}" for acc, items in sorted(shoot.items())]
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "**📷 待补拍**（拍完丢网盘待入库箱）\n" + "\n".join(lines)}})

    if not el:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "✅ 今日无待办：没要审的、没要发的、库存也够。"}})

    tip = "点标题去 base 审/发；发完把链接发我认领，或去 base 回填"
    el.append({"tag": "note", "elements": [{"tag": "lark_md", "content": tip}]})

    return {"config": {"wide_screen_mode": True},
            "header": {"template": "wathet",
                       "title": {"tag": "plain_text", "content": f"📮 {brand} · 今日面板（{config.ENV_NAME}）"}},
            "elements": el}
