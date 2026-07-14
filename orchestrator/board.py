"""面板:**agent 的眼睛**(Observation)—— 世界现在是什么样。

★这里只有事实,没有建议★

写这个文件时最容易犯的错,就是顺手加一句 `"建议": "今天该派 4 条活"` ——
**那就是把导轨装回去了**。拆掉 cadence 轮转之后本能地想"那得给它一个规则去决定",
于是规则就从 `dispatch.py` 搬进了 `board.py` 的一个字段里,换了个地方接着替它做决定。

所以本文件的纪律:
  · 报**数**(在途 4 条、上身图可用 27 张、待入库箱 6 个文件)——事实
  · 报**声明**(账号 md 说 posts_per_day=1、base 说自动排产=暂停)——事实,而且两者可能打架,如实并列
  · 报**法律**(红线是什么)——事实
  · **不报"所以你今天该干什么"** —— 那是它的判断,不是我的
"""
from __future__ import annotations

from datetime import date

from . import accounts, bitable, config, feishu_io, ingest, materials, netpan, notes, schedule
from .bitable import AccountFields as AF, AutoSched
from .bitable import InspirationFields as IF, KeywordFields as KF
from .bitable import MaterialFields as MF, MaterialStatus as MS
from .bitable import NoteFields as NF, NoteStatus as NS


# 红线(Permissions)——**焊死在代码里的法律,不是建议**。摆在眼前,免得它撞了才知道。
REDLINES = [
    f"只写测试库 {config.TEST_BASE[:6]}…(=运营库)。生产库 **读也不许碰**,守卫在任何 IO 之前。",
    "**绝不自动发布。** 出稿一律止于『草稿待发』,发布是人的动作。",
    "**绝不代勾 AI 声明。** AI 像素 → 素材『来源=AI生成』→ 门要求声明 → **人勾**。你写这个字段会被拦。",
    f"单号 ≤{config.PER_ACCOUNT_DAILY_PUBLISH} 篇/天(平台风控)。阈值焊成常量,没有旋钮。",
    "**防搬运**:产出不得含任何外来文本(爆款正文/标题/技能里的真实帖)的 ≥10 连续实义字符片段。"
    "爆款只当情报 —— 学结构,绝不抄句子。抄了出口直接拒稿。",
    "零素材的稿发不出去(小红书必须有图/视频),拦在『待发布』门外。",
]


def _accounts(brand: str) -> list[dict]:
    """每个号的**全部事实**:base 侧运营开关 + workspace 侧 md 声明 + 它的模式们。

    ⚠️ 两个真源可能打架(base 说暂停、md 说每天一条),**如实并列摆出来**,
    不在这里替它调和 —— "听谁的"本身就是判断(而且 base 是运营的驾驶舱,人点的那个开关多半是对的)。
    """
    sched = {bitable.text(r["fields"].get(AF.NAME)).strip():
             bitable.text(r["fields"].get(AutoSched.FIELD)).strip()
             for r in feishu_io.list_records(AF.TABLE)}
    out = []
    for name, acc in sorted(accounts.load_all(brand).items()):
        if acc.error:
            out.append({"账号": name, "声明坏了": acc.error})
            continue
        cad = acc.strategy.get("cadence") or {}
        out.append({
            "账号": name,
            "base「自动排产」": sched.get(name, "(账号表里没这个号)"),
            "md 声明的节奏": {"posts_per_day": cad.get("posts_per_day"), "pattern": cad.get("pattern")},
            "素材从哪来(sourcing)": acc.strategy.get("sourcing", ""),
            "库存缓冲目标(天)": acc.strategy.get("runway_alert_days"),
            "画像": f"brands/{brand}/accounts/{name}.md   ← 出稿前读它(这个号说话是什么调性)",
            "模式": [{
                "内容类型": pb.get("content_type") or pb.get("id") or "",
                "权重": pb.get("weight"),
                "gen_skill": accounts.gen_skill_of(pb),
                "技能全文": f"skills/{accounts.gen_skill_of(pb)}/SKILL.md   ← 出稿前读它(怎么写)",
                "要什么素材": pb.get("material_needs") or [],
                "篇幅规格": pb.get("body_len"),
            } for pb in acc.playbooks()],
        })
    return out


def _notes_by_status() -> dict:
    """笔记表状态分布(状态机哪一环堵着)。热态服务端过滤,不整拉表。"""
    hot = [NS.IDEA, NS.NEED_SHOOT, NS.NEED_COPY, NS.DRAFT_PENDING,
           NS.APPROVED, NS.TO_PUBLISH, NS.PUBLISHED, NS.LOOPED_BACK]
    cnt = {s: 0 for s in hot}
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, hot):
        s = bitable.text(r["fields"].get(NF.STATUS)).strip()
        if s in cnt:
            cnt[s] += 1
    return cnt


def _material_stock(brand: str) -> dict:
    """素材库存事实:每个号 × 它要的(内容 × 形态),**已拍可用几条 / 它声明的缓冲目标是几条**。

    ⚠️ 这里**不算"缺几条"、也不筛掉"够的"**。老实现(shotlist.shot_needs)是
    `if avail >= target: continue` —— 那是替 agent 决定了"够就不用催拍"。
    两个数并排摆着,**要不要发补拍单、催谁、催几条,是它的判断**。

    ⚠️ **内容(类型)和形态(图/视频)是两维**。它们曾经被焊在一个字段里,
    结果一条面料特写视频没地方放,被硬塞成「上身视频」——**凭空造出一条不存在的库存**。
    (见 bitable.MaterialForm。)现在分开数,数出来的就是真的。
    """
    rows = feishu_io.list_records(MF.TABLE)
    acc_rows = feishu_io.list_records(AF.TABLE)
    acc_id = {bitable.text(r["fields"].get(AF.NAME)).strip(): r["record_id"] for r in acc_rows}
    shot = [r for r in rows if bitable.text(r["fields"].get(MF.SHOT_STATUS)).strip() == MS.SHOT]
    by_tf: dict[str, int] = {}
    for r in shot:
        f = r["fields"]
        key = f"{bitable.text(f.get(MF.TYPE)).strip()}·{bitable.text(f.get(MF.FORM)).strip() or '?'}"
        by_tf[key] = by_tf.get(key, 0) + 1
    per_account = []
    for name, acc in sorted(accounts.load_all(brand).items()):
        if acc.error:
            continue
        rid = acc_id.get(name, "")
        target = acc.strategy.get("runway_alert_days")
        for pb in acc.playbooks():
            form = pb.get("material_form") or ""      # 这个模式要的是 图 还是 视频
            for mt in sorted(pb.get("material_needs") or []):
                avail = 0
                for r in shot:
                    f = r["fields"]
                    if bitable.text(f.get(MF.TYPE)).strip() != mt:
                        continue
                    if form and bitable.text(f.get(MF.FORM)).strip() != form:
                        continue
                    accs = bitable.link_record_ids(f.get(MF.ACCOUNTS))
                    if rid and accs and rid not in accs:
                        continue          # 显式标了别号=排除;没标=可用
                    avail += 1
                per_account.append({"账号": name, "模式": pb.get("content_type") or pb.get("id"),
                                    "要的内容": mt, "要的形态": form or "(不限)",
                                    "已拍可用": avail, "声明的缓冲目标": target})
    return {"全库已拍(内容·形态)": by_tf, "总条数": len(rows),
            "每号每模式要什么": per_account,
            "未归赛道(适用账号为空)": sum(
                1 for r in rows if not bitable.text(r["fields"].get(MF.ACCOUNTS)).strip())}


def _ideas() -> list[dict]:
    """灵感库里**还没转化成笔记**的爆款(= 蹭爆款出稿的原料)。
    正文是**情报**:学它的结构/角度,**绝不抄它的句子**(出口防搬运门比的就是它)。"""
    out = []
    for r in feishu_io.list_records(IF.TABLE):
        f = r["fields"]
        if bitable.link_record_ids(f.get(IF.CONVERTED)):
            continue                      # 已转化 → 跳过(看 link 存在性,不看显示 text,兼容 search 形态)
        title = bitable.text(f.get(IF.TITLE)).strip()
        if not title or title == "（无标题）":
            continue
        body = bitable.text(f.get(IF.BODY)).strip()
        out.append({"id": r["record_id"], "标题": title,
                    "可借鉴": bitable.text(f.get(IF.MERITS)).strip(),
                    "有正文": bool(body), "正文长度": len(body),
                    "爆款源": bitable.text(f.get(IF.LINK)).strip()})
    return out


def _feedback() -> dict:
    """回流事实:已发的帖有没有链接、有没有数据。**没数据就说没数据。**"""
    pub = feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.PUBLISHED, NS.LOOPED_BACK])
    no_link = [bitable.text(r["fields"].get(NF.TITLE)) for r in pub
               if not bitable.text(r["fields"].get(NF.PUBLISH_LINK)).strip()]
    has_data = sum(1 for r in pub if r["fields"].get(NF.LIKED) is not None)
    return {"已发/已回流": len(pub), "缺发布链接(抓不到数据)": no_link, "有点赞数据的": has_data}


def view(brand: str = "巧荷") -> dict:
    """**世界现在什么样**。一条命令看完。纯读,不写库。

    读完之后干什么 —— **你判断**。这里一个建议都没有,是故意的。"""
    return {
        "今天": str(date.today()),
        "我在哪个库": {"base": config.BASE_TOKEN[:8] + "…", "环境": config.ENV_NAME,
                       "说明": "测试库 = 运营库。TEST_MODE=1 本身就是上线态,不要去切生产库。"},
        "红线(焊死的法律,撞了会被拦)": REDLINES,
        "账号": _accounts(brand),
        "笔记状态分布": _notes_by_status(),
        "在途(还没审完/发完的)": notes.inflight(),
        "素材库存": _material_stock(brand),
        "素材类型词汇(素材表 select 的合法值)": list(ingest.MATERIAL_TYPES),
        "网盘待入库箱": {"路径": netpan.INBOX,
                         "说明": "摄影师直接往这传,不管文件名。用 `material.inbox` 看里面有什么。"},
        "灵感库(未转化的爆款)": _ideas(),
        "关键词池(启用的)": [bitable.text(r["fields"].get(KF.KEYWORD)).strip()
                             for r in feishu_io.list_records(KF.TABLE)
                             if bitable.text(r["fields"].get(KF.ENABLED)).strip() != KF.DISABLED],
        "回流": _feedback(),
        "我的作息表": schedule.list_all(),
    }
