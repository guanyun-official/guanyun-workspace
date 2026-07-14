"""今日驾驶舱(顺手:人/接手 agent 一条命令看完今日,不用挨个敲 run_day/publish_ready/shot_list)。

聚合人只管头尾要看的四件事(纯读,不写库、不触 LLM):
- 待审:草稿待发的笔记(你点批准)
- 待发:待发布的笔记 + 每条『用哪张素材+可开链接』(你手机发)
- 待回填链接:已发但还没贴发布链接的(不贴回流采集抓不到数据)
- 要补拍:库存见底的拍摄需求(你按需拍)
"""
from __future__ import annotations

from datetime import date, timedelta

from . import bitable, config, feishu_io, guard, netpan, publish, shotlist
from .bitable import NoteFields as NF, NoteStatus as NS
from .bitable import AccountFields as AF, AutoSched, ContentTypeFields as CTF


_day_start_ms = bitable.day_start_ms   # 冷热分离日期窗共用(bitable 收窄 seam;测试仍可用 cockpit._day_start_ms)


_link_names = bitable.link_names   # link 字段→显示名(三形态通吃);search 回 id 靠 name_map 还原(dogfood 坑)

# 排期视图里算「待发流程中」的状态(未发未归档;想法/待拍属前置,已发/回流/暂缓已出流程)
_SCHED_ACTIVE = frozenset({NS.NEED_COPY, NS.DRAFT_PENDING, NS.APPROVED, NS.TO_PUBLISH})


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
    # 素材只取 在途+待回填+已批准 引用的(今日已发只计数,不需素材细节)。
    # **已批准的素材必须一起取**:否则判它要不要 AI 声明时 idx 里查不到来源 → 一律算成"不需要" → 漏判红线。
    linked = [rid for r in (active + need_link_notes + approved)
              for rid in bitable.link_record_ids(r["fields"].get(NF.LINKED_MATERIALS))]
    idx = publish._material_index(linked)
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
        # AI声明需求 surface(人审前就看到⚠️;仍人自己勾):按挂的素材来源事实算,复用 guard 的法规规则
        mat_ids = bitable.link_record_ids(f.get(NF.LINKED_MATERIALS))
        ai_req = guard.ai_declaration_required([idx[m]["source"] for m in mat_ids if m in idx])
        qc = bitable.text(f.get(NF.QC)).strip()   # 质检结果(零素材/篇幅不达规格/混入制作说明…)顶到人眼前
        # **实时兜底:零素材**(2026-07-14 走运营流程发现)——落库的『质检』只在**出稿那一刻**算,
        # 历史稿/人在 base 手建的稿根本没有质检值。而真跑遇到的「OOTD｜栀子入素」就是一条**待发、
        # 零素材**的稿:运营点开 base 准备发小红书,一张图都没有,发不出去,而卡片毫无警告。
        # 所以人面必须实时判一次——不能只信落库的那个字段。
        if not mat_ids and "零素材" not in qc:
            qc = ("零素材:一张图/视频都没挂,小红书发不出去——去 base 关联素材" + ("；" + qc if qc else ""))
        if acc in paused:                        # 暂停号的稿不进待办(运营已经把这个号关了)
            paused_notes.append({"title": title, "account": acc, "mode": mode, "open": link, "质检": qc})
        elif st == NS.DRAFT_PENDING:
            pend_review.append({"title": title, "account": acc, "mode": mode, "open": link,
                                "需AI声明": ai_req, "质检": qc})
        elif st == NS.TO_PUBLISH:
            mats = publish.note_materials(f, idx)
            to_publish.append({"title": title, "account": acc, "mode": mode, "open": link,
                               "需AI声明": ai_req, "质检": qc,
                               "materials": [{"code": m["code"], "link": m["取用链接"]} for m in mats]})
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
    stuck: list[dict] = []
    for r in approved:
        f = r["fields"]
        acc = _link_names(f.get(NF.ACCOUNT), acc_names)
        mat_ids = bitable.link_record_ids(f.get(NF.LINKED_MATERIALS))
        ai_req = guard.ai_declaration_required([idx[m]["source"] for m in mat_ids if m in idx])
        why = ""
        if not mat_ids:
            why = "一张图/视频都没挂,小红书发不出去——先去 base 关联素材"
        elif ai_req and not f.get(NF.AI_DECLARED):
            why = "含 AI 合成素材,发前你得先在 base 勾『AI声明』"
        elif published.get(acc, 0) + queued.get(acc, 0) >= config.PER_ACCOUNT_DAILY_PUBLISH:
            why = (f"该号今日额度满了(已发 {published.get(acc, 0)} + 排队 {queued.get(acc, 0)} "
                   f"≥ 上限 {config.PER_ACCOUNT_DAILY_PUBLISH})——先发掉排队的,或明天再说")
        if why:
            stuck.append({"title": bitable.text(f.get(NF.TITLE)), "account": acc,
                          "mode": _link_names(f.get(NF.CONTENT_TYPE), ct_names),
                          "open": _note_link(r["record_id"]), "卡住原因": why})
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
    return {"待审": pend_review, "待发": to_publish, "待回填链接": need_link,
            "控量": quota, "要补拍": shotlist.shot_needs(brand),
            "已暂停": paused_notes,   # 暂停号的在途稿:不要人管,卡片底部提一句就够(不隐瞒也不干扰)
            "卡住": stuck}            # 批了却被门拦下的稿:**必须让人看见**,否则批完就消失=黑洞


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
            mark = " ⚠️AI声明" if n.get("需AI声明") else ""   # surface:含AI合成素材,发前须人勾AI声明
            line = f"{icon} {_title_link(n)}{mark}"
            # **质检警告必须出现在卡片上**(2026-07-14 运营视角实测的代价):零素材的废稿(小红书没图
            # 发不了)、篇幅不达技能规格的短稿,原来静静躺在待审区,卡片一个字提示都没有——人得点进去
            # 才发现是废稿。算了不给人看 = 等于没检。
            if n.get("质检"):
                line += f"\n     ⚠️ {n['质检']}"
            blocks.setdefault(key, []).append(line)

    el: list[dict] = []
    # **agent 今天的判断,必须传到运营眼前**(2026-07-14 以 agent 身份上班撞到)。
    # 我看到队列积压 4 条待审,判断"今天不派新活,先催审" —— 系统也同意(干跑 0 条)。
    # 可这句话**只印在终端里**,而运营不敲终端。他打开卡片看到 4 个光秃秃的标题,
    # 不知道系统在等他,更不知道"我不动是因为你没动"。
    # **算了、判了,却没给人看 —— 等于没判。**
    n_wait = len(p["待审"])
    if n_wait:
        # ⚠️ 措辞必须只说**确凿为真**的话。我第一版写的是「今天没派新活」——
        # 那是**未经核实的断言**:没有待审稿的号今天照样会派。差点亲手写下一句骗人的话,
        # 而"话在骗人"正是我今天一路在拆的那个病。
        # 确凿为真的只有这一条(去重是写死的行为):**同号同模式,在途没审完就不会再派**。
        el.append({"tag": "div", "text": {"tag": "lark_md", "content":
                   f"**🖊 等你审的 {n_wait} 条**（点标题去 base，把『状态』改掉就行）\n"
                   f"⏸ 这些审完之前，**同号同模式不会再派新活**（免得给你堆稿）。"
                   f"审掉一条(批准 / 暂缓归档)，那个号的位子就空出来了。"}})
    for (acc, mode), lines in sorted(blocks.items()):
        head = f"**{acc}{' · ' + mode if mode else ''}**"
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": head + "\n" + "\n".join(lines)}})

    # **卡住的稿**:你批了,但系统被门拦住没敢往下推。不喊出来 = 稿子在人面上消失 = 你以为发了其实没发。
    if p.get("卡住"):
        el.append({"tag": "hr"})
        lines = [f"· {_title_link(n)}（{n['account']}）\n     ↳ {n['卡住原因']}" for n in p["卡住"]]
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": "**🛑 你批了、但发不出去的**（卡在门前，需要你处理）\n" + "\n".join(lines)}})

    # 控量预警(红线):今日额度占用逼近单号日上限→标红,防超发(assert_publish_quota 曾是死码,这里给人看)
    hot = [q for q in p.get("控量", []) if q["逼近"]]
    if hot:
        el.append({"tag": "hr"})
        # 话要说得让人一眼懂自己到底发没发:「今日已发 X 条 + 排队 Y 条 = 占满 Z/上限」
        lines = [f"· {q['account']}：今日已发 {q['今日已发']} 条 + 排队待发 {q['排队待发']} 条 "
                 f"= 占用 {q['占用']}/{q['上限']}，别再排新的了" for q in hot]
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": f"**🚦 控量预警**（红线：单号日发 ≤ {config.PER_ACCOUNT_DAILY_PUBLISH}）\n" + "\n".join(lines)}})

    # 补拍:**带上"怎么拍"和"照着什么拍"**(2026-07-14 运营视角实测)——原来卡片上只有干巴巴一行
    # 「ootd号:上身视频×3」,而调性和参考画面只存在于 shot_list 这个 CLI 里。**运营不敲终端**,
    # 他手机上收到卡片,只知道"要拍3条",不知道怎么拍、照着什么拍 → 补拍单的人面是断的。
    if p["要补拍"]:
        el.append({"tag": "hr"})
        lines = []
        for s in p["要补拍"]:
            lines.append(f"· **{s['account']}**：{s['类型']} × {s['缺']} 条")
            if s.get("拍摄要求"):
                lines.append(f"   {s['拍摄要求']}")
            if s.get("参考"):
                lines.append(f"   {s['参考']}")
        # 别再承诺"文件名带类型更好认"——系统**根本不读文件名**,分类全由 vision 看图决定。
        # 实测:文件命名成「ootd号·上身图」,系统标出来是「商品图」(豆包看图判对了,是命名错了)。
        # 让人白费功夫按规范命名 = 典型的"人想起来方便的逻辑,落实下来是 bug"。
        lines.append(f"\n拍完丢网盘：`{netpan.INBOX}`（**直接传，不用管文件名** —— 系统看图自动归类）")
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": "**📷 待补拍**\n" + "\n".join(lines)}})

    # 暂停号:它的稿不进待办(运营已经把号关了),但也别偷偷藏起来——底部提一句,想看点 base
    if p.get("已暂停"):
        el.append({"tag": "hr"})
        accs = sorted({n["account"] for n in p["已暂停"]})
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": f"**⏸ 已暂停的号**（base 里「自动排产=暂停」，不用管）\n"
                              f"· {'、'.join(accs)}：还有 {len(p['已暂停'])} 条旧稿在库里"}})

    if not el:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "✅ 今日无待办：没要审的、没要发的、库存也够。"}})

    # **别说人做不到的事**(2026-07-14 人眼审抓到的假承诺):原文是"发完把链接发我认领,或去 base 回填"
    # —— "发我认领"要 webhook 接住聊天消息 → `publish.fill_publish_link()` 是那个入口,
    # 而它**生产零调用、webhook 未接**:运营真把链接发给 bot,**石沉大海,没有任何东西在听**。
    # 功能没接线,话却已经说出去了。改成他**真能做**的:去 base 改状态+填链接。
    # 『实际发布日』他做不了,系统在 publish_ready(cron)里自愈补上(stamp_published_at)——
    # 别再要求人做一件他做不到的事。
    tip = "点标题去 base：审就改『状态』，发完把小红书链接填进『发布链接』并把状态改成『已发』（发布日系统自动补）"
    el.append({"tag": "note", "elements": [{"tag": "lark_md", "content": tip}]})

    return {"config": {"wide_screen_mode": True},
            "header": {"template": "wathet",
                       "title": {"tag": "plain_text", "content": f"📮 {brand} · 今日面板（{config.ENV_NAME}）"}},
            "elements": el}


def _bucket_schedule(records: list[dict], today: date, days: int = 7,
                     acc_names: dict | None = None, ct_names: dict | None = None) -> dict:
    """本周排期的**纯分桶逻辑**(零网络,records/today 注入 → 直测):把『待发流程中』的笔记
    按『计划发布日』分到未来 days 天;无日期→未排期(日滴待铺);日期已过且未发→逾期(漏发提醒)。
    素材一股脑拍→笔记增量产,这视图就是『增量显示每天的』——空日不进(见 card 只显有货日)。
    acc_names/ct_names = id→名映射(search 的 link 字段只回 id;注入以还原账号/内容类型显示名)。"""
    acc_names = acc_names or {}
    ct_names = ct_names or {}
    horizon: dict[date, list[dict]] = {today + timedelta(d): [] for d in range(max(1, days))}
    unplanned: list[dict] = []
    overdue: list[dict] = []
    for r in records:
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        if st not in _SCHED_ACTIVE:
            continue
        item = {"title": bitable.text(f.get(NF.TITLE)),
                "account": _link_names(f.get(NF.ACCOUNT), acc_names),      # 三形态通吃(含回退 text)
                "mode": _link_names(f.get(NF.CONTENT_TYPE), ct_names),
                "status": st, "open": _note_link(r["record_id"])}
        planned = bitable.parse_ts(f.get(NF.PLANNED_AT))
        if planned is None:
            unplanned.append(item)
        elif planned.date() in horizon:
            horizon[planned.date()].append(item)
        elif planned.date() < today:
            overdue.append(item)
        # 超出 horizon(>days 天后)→ 本周视图先不显示
    dow = "一二三四五六日"
    out_days = [{"date": f"{d:%m-%d}", "weekday": dow[d.weekday()], "notes": horizon[d]}
                for d in sorted(horizon)]
    return {"days": out_days, "未排期": unplanned, "逾期": overdue}


def weekly_schedule(brand: str = "巧荷", today: date | None = None, days: int = 7) -> dict:
    """本周排期增量视图(纯读):IO 边界取笔记 → `_bucket_schedule` 纯逻辑分桶。today 默认今天(注入可测)。"""
    # 状态∈待发流程中 服务端过滤(规模M2,不全拉笔记表);_bucket_schedule 再按 _SCHED_ACTIVE 分桶(等价)
    return _bucket_schedule(feishu_io.search_in(NF.TABLE, NF.STATUS, list(_SCHED_ACTIVE)),
                            today or date.today(), days,
                            acc_names=feishu_io.name_map(AF.TABLE, AF.NAME),      # search link 只回 id→还原名
                            ct_names=feishu_io.name_map(CTF.TABLE, CTF.NAME))


def weekly_schedule_card(brand: str = "巧荷", view: dict | None = None) -> dict:
    """本周排期 → 飞书卡片。只显有货的日(增量)+ 逾期 + 未排期(待铺发布日)。纯函数(view 可注入直测)。"""
    v = view if view is not None else weekly_schedule(brand)
    el: list[dict] = []
    for day in v["days"]:
        if not day["notes"]:
            continue   # 空日不占版面(增量:只显有货日)
        lines = [f"· {n['account']}{' · ' + n['mode'] if n['mode'] else ''} {_title_link(n)}"
                 for n in day["notes"]]
        el.append({"tag": "div", "text": {"tag": "lark_md",
                   "content": f"**{day['date']} 周{day['weekday']}**\n" + "\n".join(lines)}})
    for icon, key, hint in (("⏰", "逾期", "逾期未发"), ("🗂", "未排期", "待铺发布日")):
        if v[key]:
            el.append({"tag": "hr"})
            lines = [f"· {n['account']}{' · ' + n['mode'] if n['mode'] else ''} {_title_link(n)}"
                     for n in v[key]]
            el.append({"tag": "div", "text": {"tag": "lark_md",
                       "content": f"**{icon} {key}**（{len(v[key])}条·{hint}）\n" + "\n".join(lines)}})
    if not el:
        el.append({"tag": "div", "text": {"tag": "lark_md", "content": "本周无排期笔记。"}})
    el.append({"tag": "note", "elements": [{"tag": "lark_md",
               "content": "在 base 给笔记填『计划发布日』即排进对应日；未排期=日滴待铺"}]})
    return {"config": {"wide_screen_mode": True},
            "header": {"template": "turquoise",
                       "title": {"tag": "plain_text", "content": f"🗓 {brand} · 本周排期（{config.ENV_NAME}）"}},
            "elements": el}
