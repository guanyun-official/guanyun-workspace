"""拍摄需求单(『头』侧:人只管头尾的头=按需/自主拍素材,这里告诉他"需要拍什么")。

素材『一次性拍完』的场景 → 这是**补货信号**:每号×素材类型,比『目标缓冲(runway_alert_days 条)』和
『已拍可用库存(赛道过滤)』——够就不提,快见底才提该号补拍哪类、缺几条,并附**拍摄要求 brief**(人设/调性/
照哪个技能风格)+ **参考**(该 gen_skill 的真实帖 few-shot + 该号画像)。

纯读(不写库),给人看/推飞书。回答"需要拍什么在哪看、怎么表达":看这单;表达=类型+条数+brief+参考帖。
"""
from __future__ import annotations

from . import accounts, bitable, draft, feishu_io, netpan
from .bitable import AccountFields as AF, MaterialFields as MF


def _deliver_to(name: str, mtype: str) -> str:
    """人拍完/生成后往哪丢(答"人拍完怎么给到"):单一扁平投递箱,文件名带号·类型更好认(不带也行,打标技能会自动归类=容错)。"""
    return f"传网盘 {netpan.INBOX}/(文件名带『{name}·{mtype}』更好认;不带也行,系统会看图自动归类)"


def _brief(name: str, acc, mtype: str, gen_skill: str) -> str:
    """一条拍摄要求:拍什么类型 + 该号人设/调性(取 md notes 提要)+ 照哪个技能的真实帖风格。"""
    notes = (acc.strategy.get("notes") or "").split(";")[0].strip()
    return f"拍『{mtype}』:{notes or name} 调性;风格照技能『{gen_skill}』的真实帖 few-shot + 该号画像挑最出片的"


def shot_needs(brand: str = "巧荷") -> list[dict]:
    """拍摄需求单:每号×素材类型,库存(已拍可用)< 目标缓冲 才提。
    返回 [{account, 类型, 缺, 已有, 目标, 拍摄要求, 参考}](缺=目标-已有,>0 才在单里)。"""
    accs = {n: a for n, a in accounts.load_all(brand).items() if not a.error}
    # 全局需要的素材类型 → 一次按类型服务端过滤取素材(规模M4,不全拉素材表)
    needed = sorted({mt for a in accs.values()
                     for pb in a.playbooks() for mt in (pb.get("material_needs") or [])})
    mats = feishu_io.search_in(MF.TABLE, MF.TYPE, needed)
    acc_id = {bitable.text(r["fields"].get(AF.NAME)).strip(): r["record_id"]
              for r in feishu_io.list_records(AF.TABLE)}
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
            avail = len(draft._material_hits(mats, [mtype], rid, limit=9999))   # 已拍+赛道 可用库存
            if avail >= target:
                continue                                                        # 库存够→不提
            out.append({"account": name, "类型": mtype, "缺": target - avail, "已有": avail,
                        "目标": target, "拍摄要求": _brief(name, acc, mtype, gen_skill),
                        "投递去向": _deliver_to(name, mtype),
                        "参考": f"local-skills/{gen_skill}/SKILL.md 真实帖 + brands/{brand}/accounts/{name}.md 画像"})
    return out
