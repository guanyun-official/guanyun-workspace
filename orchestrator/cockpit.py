"""今日卡片(**给运营看的** · Observation · 人面)。纯读,不写库。

他只管头尾,不敲终端。这张卡告诉他今天要做的三件事:待审 / 待发 / 待回填链接,
外加**卡住的稿**(他批了、但被门拦下 —— 不喊出来,稿子在人面上就消失了)、控量预警、暂停号。

★门的判定只有一份真源★ ——「为什么卡住」直接转达 `publish.review_approved()` 的话,
这里**绝不自己再判一遍**(那会让人面和门说不一样的话)。
"""
from __future__ import annotations

from datetime import date

from . import bitable, config, feishu_io, publish
from .bitable import NoteFields as NF, NoteStatus as NS
from .bitable import AccountFields as AF, AutoSched, ContentTypeFields as CTF


_day_start_ms = bitable.day_start_ms   # 冷热分离日期窗共用(bitable 收窄 seam;测试仍可用 cockpit._day_start_ms)


_link_names = bitable.link_names   # link 字段→显示名(三形态通吃);search 回 id 靠 name_map 还原(dogfood 坑)

def _note_link(record_id: str) -> str:
    """这条笔记在 base 里的深链(飞书聊天里一点直达该行去审/改)——『引导到 base 操作』。"""
    try:
        return config.record_url(NF.TABLE, record_id)
    except Exception:  # noqa: BLE001  schema 缺表名等 → 不给链接也不炸
        return ""


def today_panel(brand: str = "巧荷") -> dict:
    """今日面板:分出 待审/待发/待回填链接/控量/要补拍。纯读。每条笔记带 base 深链(引导到 base 操作)。
    **冷热分离(规模M4)**:已发是累积态,绝不整表拉——
    - 热(在途,本就小):草稿待发+待发布 走 search_in;
    - 待回填链接:状态=已发 AND 发布链接 isEmpty(服务端复合过滤,实测真跑);
    - 今日已发(控量额度):状态=已发 AND 实际发布日≥今天0点(服务端日期窗)。
    万级已发时只拉命中的少数行,不再随历史线性膨胀。"""
    day0 = str(_day_start_ms(date.today()))
    _pub = {"field_name": NF.STATUS, "operator": "is", "value": [NS.PUBLISHED]}
    active = feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.DRAFT_PENDING, NS.TO_PUBLISH])   # 在途,小
    need_link_notes = feishu_io.search_records(NF.TABLE, [                                  # 已发缺链接(待回填)
        _pub, {"field_name": NF.PUBLISH_LINK, "operator": "isEmpty", "value": []}], conjunction="and")
    pub_today = feishu_io.search_records(NF.TABLE, [                                        # 今日已发(控量额度)
        _pub, {"field_name": NF.PUBLISHED_AT, "operator": "isGreater", "value": ["ExactDate", day0]}],
        conjunction="and")
    approved = feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.APPROVED])   # 过渡态(在途,小):可能卡在门前
    # 面板 = 导航索引:只取标题/账号/模式/深链,不拉素材、不算质检/他牌/AI声明(2026-07-15 运营反馈:
    # 那些 base 里都有,点标题进去看就行)。门的判定走 publish.review_approved() 独立路径,不依赖这里。
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)      # link 字段从 search 只回 id→靠小表 id→名还原显示
    ct_names = feishu_io.name_map(CTF.TABLE, CTF.NAME)
    # **暂停号的稿不进运营待办**(2026-07-14 运营视角实测):官号 base 里「自动排产=暂停」,
    # 可它的稿照样躺在待审区要人审——运营的心智是"官号我关了",卡片却让他审官号,纯干扰。
    # 不是隐瞒:单独归到『已暂停』,卡片底部一行提示,人想看点 base。
    paused = {bitable.text(r["fields"].get(AF.NAME)).strip()
              for r in feishu_io.list_records(AF.TABLE)
              if bitable.text(r["fields"].get(AutoSched.FIELD)).strip() == AutoSched.PAUSED}
    pend_review: list[dict] = []
    to_publish: list[dict] = []
    need_link: list[dict] = []
    paused_notes: list[dict] = []      # 暂停号的在途稿:不要人管,只提一句
    # 控量(红线):**已发**和**排队**分开记——两者相加才是额度占用(防超发),但对人要分开讲清楚,
    # 否则卡片上「今日 4/3 已达上限」会让今天一条没发的运营懵掉(那 4 其实是排队数)。
    published: dict[str, int] = {}   # 今日真发出去的(实际发布日=今天)
    queued: dict[str, int] = {}      # 排队待发的(占额度,但还没发)
    for r in active:
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        title = bitable.text(f.get(NF.TITLE))
        acc = _link_names(f.get(NF.ACCOUNT), acc_names)
        link = _note_link(r["record_id"])
        mode = _link_names(f.get(NF.CONTENT_TYPE), ct_names)
        if acc in paused:                        # 暂停号的稿不进待办(运营已经把这个号关了)
            paused_notes.append({"title": title, "account": acc, "mode": mode, "open": link})
        elif st == NS.DRAFT_PENDING:
            pend_review.append({"title": title, "account": acc, "mode": mode, "open": link})
        elif st == NS.TO_PUBLISH:
            to_publish.append({"title": title, "account": acc, "mode": mode, "open": link})
            queued[acc] = queued.get(acc, 0) + 1          # 排队待发(占额度,但**还没发**)
    for r in need_link_notes:
        f = r["fields"]
        need_link.append({"title": bitable.text(f.get(NF.TITLE)),
                          "account": _link_names(f.get(NF.ACCOUNT), acc_names),
                          "mode": _link_names(f.get(NF.CONTENT_TYPE), ct_names), "open": _note_link(r["record_id"])})
    for r in pub_today:
        acc = _link_names(r["fields"].get(NF.ACCOUNT), acc_names)
        published[acc] = published.get(acc, 0) + 1        # **今日真发出去的**(实际发布日=今天)

    # **卡住的稿**(2026-07-14 走运营流程发现的黑洞):『已批准』是**过渡态**——系统本该把它推进到
    # 『待发布』,但被门拦下时(AI声明未勾 / 控量已满)它就**停在这儿**。而 today_panel 原来只看
    # 『草稿待发』和『待发布』两个状态 → 这条稿**在人面上彻底消失**:运营批准完就再也看不到它,
    # 会以为发出去了。门拦住不等于事情办完了——**拦住 + 告诉人为什么 + 告诉人该干什么**,才算数。
    # ★门的判定只有一份真源:`publish.review_approved()`★(2026-07-14 verify 抓到)
    #
    # 老实现在这里**把三道门又写了一遍**(零素材 → AI声明 → 控量的 if/elif),还**自己重算了额度**。
    # 而且两边的**键不一样**:`publish._account_load()` 按 **record_id** 记额度,这里按**账号显示名**记
    # —— 同名 / 改名 / link 解析不出来的时候,**两个数会分叉**,
    # 于是**人面上写的"卡住原因"会和门的真实判定说不一样的话**。
    #
    # 门是什么、为什么拦、怎么办 —— **只有门自己知道**。这里只负责**把它的话转达给人**。
    verdicts = {e["note_id"]: e["verdict"] for e in publish.review_approved(brand, write=False)}
    stuck: list[dict] = []
    for r in approved:
        v = verdicts.get(r["record_id"], "")
        if not v.startswith("⚠️"):          # 门放行了 → 不是"卡住",它只是还没被推进
            continue
        f = r["fields"]
        stuck.append({"title": bitable.text(f.get(NF.TITLE)),
                      "account": _link_names(f.get(NF.ACCOUNT), acc_names),
                      "mode": _link_names(f.get(NF.CONTENT_TYPE), ct_names),
                      "open": _note_link(r["record_id"]),
                      "卡住原因": v.lstrip("⚠️")})   # ← 门自己的话,一个字不改
    cap = config.PER_ACCOUNT_DAILY_PUBLISH
    # **把"已发"和"排队"拆开说**(2026-07-14 运营视角实测):原来两者相加塞进一个数、还叫「今日」,
    # 卡片上写「ootd号:今日 4/3 已达上限」——可 ootd号今天**一条都没发**,那 4 是排队待发的稿数。
    # 数字没错(占额度防超发的逻辑是对的),但**话在骗人**:人读到的是"我今天发了4条"。
    # 现在分开:今日已发 X 条 + 排队 Y 条 = 占用 Z/上限。人一眼知道自己到底发没发。
    quota = [{"account": a,
              "今日已发": published.get(a, 0),
              "排队待发": queued.get(a, 0),
              "占用": published.get(a, 0) + queued.get(a, 0),
              "上限": cap,
              "逼近": published.get(a, 0) + queued.get(a, 0) >= cap}
             for a in sorted(set(published) | set(queued))
             if published.get(a, 0) + queued.get(a, 0)]
    # **补拍不在这张卡上算**(2026-07-14 拆导轨):"库存够不够、该不该催拍、催几条、怎么跟摄影师说"
    # 全是判断,已交回 agent —— 它看 board 的库存事实,自己判断,自己用 `shotlist` 发一张补拍单。
    # 这里再算一遍 = 判断有两份真源,而且我这份还只会做减法(`目标 - 已有`),压根不看今天有没有活。
    return {"待审": pend_review, "待发": to_publish, "待回填链接": need_link,
            "控量": quota,
            "已暂停": paused_notes,   # 暂停号的在途稿:不要人管,卡片底部提一句就够(不隐瞒也不干扰)
            "卡住": stuck}            # 批了却被门拦下的稿:**必须让人看见**,否则批完就消失=黑洞


def _title_link(n: dict) -> str:
    """笔记 → 可点标题(base 深链;点进去素材/文案都在,卡片不再堆细节)。"""
    t = n["title"] or "(无标题)"
    return f"[{t}]({n['open']})" if n.get("open") else t


def today_card(brand: str = "巧荷", panel: dict | None = None) -> dict:
    """今日面板 → 飞书交互卡片(高级组件 · 干净专业)。

    面板 = **导航索引**(运营反馈):每个账号·模式下只列**可点笔记标题**,用图标区分
    📋待审 / 📤待发 / 🔗待回填。**质检/logo/撞衫/AI声明等提示全部去掉** —— 那些 base
    里都有,点标题进去看就行,面板只当索引用。

    视觉层次:
      - header:彩色头(template=wathet 蓝)+ 副标题(环境名)
      - 顶部摘要 div:『今天要你做的:N 条待审 / N 条待发 / N 条待回填』
      - hr 分隔
      - 每个(账号·模式)一个 section:column_set 左列放分组头(账号·模式),右列放标题列表
      - 卡住 / 控量 / 暂停号仍保留(这些**不在 base 里**,是门和红线算出来的,必须喊出来)
      - 底部 note:『点标题去 base 操作 …』
    纯函数(panel 可注入直测)。
    """
    p = panel if panel is not None else today_panel(brand)

    # ── 按 (账号, 模式) 归块;块内按状态给图标;**只留可点标题+图标**,无质检文字 ──
    blocks: dict[tuple, list[str]] = {}
    for icon, bucket in (("📋", "待审"), ("📤", "待发"), ("🔗", "待回填链接")):
        for n in p[bucket]:
            key = (n["account"], n.get("mode", ""))
            blocks.setdefault(key, []).append(f"{icon} {_title_link(n)}")

    el: list[dict] = []

    # ── 顶部摘要:今天要你做的 ──
    n_wait, n_pub, n_link = len(p["待审"]), len(p["待发"]), len(p["待回填链接"])
    summary_parts = []
    if n_wait:
        summary_parts.append(f"📋 **{n_wait} 条待审**")
    if n_pub:
        summary_parts.append(f"📤 **{n_pub} 条待发**")
    if n_link:
        summary_parts.append(f"🔗 **{n_link} 条待回填**")
    if summary_parts:
        el.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**今天要你做的**  ·  " + "  ·  ".join(summary_parts)
                           + "\n<text color='grey'>图标说明:📋 待审  ·  📤 待发  ·  🔗 待回填链接</text>"
            }
        })
        el.append({"tag": "hr"})

    # ── 按 账号·模式 分块 ──
    if blocks:
        for (acc, mode), lines in sorted(blocks.items()):
            section_label = f"**{acc}**" + (f"  <text color='grey'>· {mode}</text>" if mode else "")
            el.append({
                "tag": "div",
                "fields": [
                    {"is_short": False, "text": {"tag": "lark_md", "content": section_label}},
                ]
            })
            # 标题列表:每条一行,纯图标+可点标题(无质检文字)
            el.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(lines)}
            })
            el.append({"tag": "hr"})
        # 末尾多一条 hr 是给后续 section 用的;若无后续 section,去掉
        el.pop()
    else:
        el.append({
            "tag": "div",
            "text": {"tag": "lark_md",
                     "content": "<text color='grey'>✅ 今日无待办:没要审的、没要发的。</text>"}
        })

    # ── 卡住的稿:你批了,但被门拦下(**不在 base 状态里显式可见**,必须喊) ──
    if p.get("卡住"):
        el.append({"tag": "hr"})
        lines = [f"· {_title_link(n)}（{n['account']}）\n     ↳ {n['卡住原因']}" for n in p["卡住"]]
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": "**🛑 你批了、但发不出去的**\n<text color='grey'>卡在门前,需要你处理</text>\n"
                              + "\n".join(lines)}})

    # ── 控量预警(红线) ──
    hot = [q for q in p.get("控量", []) if q["逼近"]]
    if hot:
        el.append({"tag": "hr"})
        lines = [f"· **{q['account']}**:今日已发 {q['今日已发']} 条 + 排队 {q['排队待发']} 条 "
                 f"= 占用 {q['占用']}/{q['上限']}" for q in hot]
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": f"**🚦 控量预警**\n<text color='grey'>红线:单号日发 ≤ {config.PER_ACCOUNT_DAILY_PUBLISH}</text>\n"
                              + "\n".join(lines)}})

    # ── 暂停号 ──
    if p.get("已暂停"):
        el.append({"tag": "hr"})
        accs = sorted({n["account"] for n in p["已暂停"]})
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": "**⏸ 已暂停的号**\n"
                              f"<text color='grey'>{'、'.join(accs)}:还有 {len(p['已暂停'])} 条旧稿在库里,不用管</text>"}})

    # ── 底部操作提示 ──
    tip = ("点标题直达 base 对应行。审 → 改『状态』;发完 → 填『发布链接』+ 状态改『已发』"
           "+ 填『实际发布日』(控量红线靠它算)。")
    el.append({"tag": "note", "elements": [{"tag": "lark_md", "content": tip}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "wathet",
            "title": {"tag": "plain_text", "content": f"📮 {brand} · 今日面板"},
            "subtitle": {"tag": "plain_text", "content": f"{config.ENV_NAME}  ·  运营待办索引"}
        },
        "elements": el
    }


