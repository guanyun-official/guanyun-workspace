"""拍摄需求单(『头』侧:人只管头尾的头=按需/自主拍素材,这里告诉他"需要拍什么")。

素材『一次性拍完』的场景 → 这是**补货信号**:每号×素材类型,比『目标缓冲(runway_alert_days 条)』和
『已拍可用库存(赛道过滤)』——够就不提,快见底才提该号补拍哪类、缺几条,并附**拍摄要求 brief**(人设/调性/
照哪个技能风格)+ **参考**(该 gen_skill 的真实帖 few-shot + 该号画像)。

纯读(不写库),给人看/推飞书。回答"需要拍什么在哪看、怎么表达":看这单;表达=类型+条数+brief+参考帖。
"""
from __future__ import annotations

from . import accounts, bitable, draft, feishu_io, netpan
from .bitable import AccountFields as AF, AutoSched, MaterialFields as MF


def _deliver_to(name: str, mtype: str) -> str:
    """人拍完/生成后往哪丢(答"人拍完怎么给到"):单一扁平投递箱,文件名带号·类型更好认(不带也行,打标技能会自动归类=容错)。"""
    return f"传网盘 {netpan.INBOX}/(文件名带『{name}·{mtype}』更好认;不带也行,系统会看图自动归类)"


def _brief(name: str, acc, mtype: str, gen_skill: str) -> str:
    """一条拍摄要求 —— **写给拿相机的人看的**,不是写给 agent 看的。

    2026-07-14 运营视角实测:原文是「风格照技能『writing-ootd-caption』的真实帖 few-shot + 该号画像
    挑最出片的」——让摄影师去读代码库里的 SKILL.md?他在片场,手机上收到这条,打不开也看不懂。
    现在只给人话:这个号是什么调性(取账号画像的一句话)+ 拍什么。参考画面由 `_reference_shots` 给
    (真图 + 网盘链接,照着拍)。gen_skill 是给出稿用的,与拍摄无关,不往人眼前塞。
    """
    # 画像是一份 md,**首行是标题/来源元数据**(「# ootd号 · 账号画像」「> 来源:xhs-extract 实抓…」),
    # 直接取首句会把这些塞给摄影师。跳过 markdown 标题/引用/空行,找**第一句实质的调性描述**。
    tone = ""
    for ln in (acc.profile_text or "").splitlines():
        s = ln.strip().lstrip("*- ").strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|"):
            continue
        tone = s.replace("**", "")[:80]
        break
    if not tone:   # 画像没有实质内容 → 退回账号 md 的 notes(滤掉给系统看的那几段)
        notes = [x.strip() for x in (acc.strategy.get("notes") or "").split(";") if x.strip()]
        useful = [x for x in notes if x != name and "走 " not in x and "文案 " not in x]
        tone = "、".join(useful[:2]) or name
    return f"拍『{mtype}』——{tone}"


def shot_needs(brand: str = "巧荷") -> list[dict]:
    """拍摄需求单:每号×素材类型,库存(已拍可用)< 目标缓冲 才提。
    返回 [{account, 类型, 缺, 已有, 目标, 拍摄要求, 参考}](缺=目标-已有,>0 才在单里)。"""
    accs = {n: a for n, a in accounts.load_all(brand).items() if not a.error}
    acc_rows = feishu_io.list_records(AF.TABLE)
    # **暂停号不催拍**(2026-07-14 运营视角实测):官号 base 里「自动排产=暂停」,补拍单却还在催
    # 运营去拍官号的上身视频×4——号都关了还让人去拍?纯干扰,人会开始无视这张单(狼来了)。
    # base 的「自动排产」是运营开关的唯一真相(md 只是默认值),这里必须听它。
    paused = {bitable.text(r["fields"].get(AF.NAME)).strip()
              for r in acc_rows
              if bitable.text(r["fields"].get(AutoSched.FIELD)).strip() == AutoSched.PAUSED}
    accs = {n: a for n, a in accs.items() if n not in paused}
    # 全局需要的素材类型 → 一次按类型服务端过滤取素材(规模M4,不全拉素材表)
    needed = sorted({mt for a in accs.values()
                     for pb in a.playbooks() for mt in (pb.get("material_needs") or [])})
    mats = feishu_io.search_in(MF.TABLE, MF.TYPE, needed) if needed else []
    acc_id = {bitable.text(r["fields"].get(AF.NAME)).strip(): r["record_id"] for r in acc_rows}
    out: list[dict] = []
    for name, acc in sorted(accs.items()):
        if acc.error:
            continue
        target = int(acc.strategy.get("runway_alert_days") or 3)   # 目标缓冲(条,≈够发几天)
        rid = acc_id.get(name, "")
        # 该号所有模式需要的素材类型 → 各自的风格技能(取第一个用到该类型的模式的 gen_skill)
        type_skill: dict[str, str] = {}
        for pb in acc.playbooks():
            for mt in (pb.get("material_needs") or []):
                type_skill.setdefault(mt, accounts.gen_skill_of(pb))
        for mtype, gen_skill in sorted(type_skill.items()):
            hit_ids = draft._material_hits(mats, [mtype], rid, limit=9999)      # 已拍+赛道 可用库存
            avail = len(hit_ids)
            if avail >= target:
                continue                                                        # 库存够→不提
            out.append({"account": name, "类型": mtype, "缺": target - avail, "已有": avail,
                        "目标": target, "拍摄要求": _brief(name, acc, mtype, gen_skill),
                        "投递去向": _deliver_to(name, mtype),
                        "参考": _reference_shots(mats, hit_ids)})
    return out


def _reference_shots(mats: list[dict], hit_ids: list[str], k: int = 2) -> str:
    """参考:**该号已有的同类素材长什么样**(豆包 vision 标 + 可点开的链接)——照着这个拍。

    2026-07-14 运营视角实测:原来这里给的是
      `skills/writing-ootd-caption/SKILL.md 真实帖 + brands/巧荷/accounts/ootd号.md 画像`
    ——**这是写给 agent 的文件路径,不是写给人的**。运营在手机上收到补拍单,让他去打开代码库里的
    SKILL.md?他不在终端,他打不开。补拍单的读者是**拿相机的人**,给他的必须是能直接看的画面。
    """
    by_id = {m["record_id"]: m for m in mats}
    refs = []
    for rid in hit_ids[:k]:
        f = (by_id.get(rid) or {}).get("fields", {})
        note = bitable.text(f.get(MF.NOTE)).strip()
        link = f.get(MF.LINK)
        url = link.get("link") if isinstance(link, dict) else ""
        if note:
            refs.append(f"「{note[:44]}」" + (f" → {url}" if url else ""))
    if not refs:
        return "(该号这类素材还一条都没有——第一次拍,按上面的调性自由发挥)"
    return "照着这些已有的拍(同调性,换场景/角度别重样):\n      · " + "\n      · ".join(refs)
