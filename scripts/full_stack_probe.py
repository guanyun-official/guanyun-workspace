#!/usr/bin/env python3
"""全链路真跑压测台(GOAL:实测全体系·全链路·全情景·全角度压测都实际通过)。

**为什么存在**:keep 门(pytest / ar_check / check_p)测的是"代码和 mock 自洽";dogfood_smoke 只冒烟 5 条。
真正会砸在运营脸上的问题,只有**把整条链路当真人真跑一遍**才暴露——2026-07-14 一天里真跑抓到的:
  · 文案根本没看过素材(先写后挑图)→ 编面料手感,货不对板
  · claude -p 每次白吞 33K token 系统提示 → 一条文案 3 元(贵 577 倍)
  · 制作说明【视频剪辑要点】混进要发的文案 → 运营复制就发出去
  · 质检守着永远撞不到的天花板 → 4 条真稿零命中
  · 『被引用次数』formula 恒返 0 → 少用优先是死机制 → 133 条素材只用前 3 条,3 个号撞图
  · 官号零素材废稿("✅无问题")→ 小红书没图发不了
这些**没有一条**是绿门能抓到的。所以判定"能用"看这里,不看绿门。

覆盖:L1-L17 全链路 + 压测角度(坏数据/红线穿透/规模/边界/新号冷启/超量)。
真库 ZhzJbf、真 ARK、真 lark-cli。**绝不自动发布、绝不代勾 AI 声明、绝不碰生产库**。

  python3 scripts/full_stack_probe.py              # 全跑(含真出稿,真花钱;单条稿约 0.006 元)
  python3 scripts/full_stack_probe.py --no-llm     # 跳过真出稿(省钱,但 L4 只验管道不验文案)
  python3 scripts/full_stack_probe.py --only L4,L7 # 只跑指定链路
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL: list[str] = []
SKIP: list[str] = []


def ck(link: str, what: str, ok: bool, detail: str = "") -> bool:
    """断言一件**人能看懂的真事**。假 → 记账 + 非0退出(是闸不是报告)。"""
    mark = "✓" if ok else "✗"
    print(f"    {mark} {what}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAIL.append(f"{link}: {what}" + (f" ({detail})" if detail else ""))
    return ok


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    """真跑一条 CLI(cron/agent 真实调用它们的方式),返回 (退出码, 输出)。"""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def section(link: str, title: str) -> None:
    print(f"\n── {link} {title} " + "─" * max(0, 56 - len(title)))


# ══════════════════════════════════════════════════════════════════════════════
# L1 素材入库:网盘→打标→落素材表。断言:类型对/来源就低(AI落AI)/有缩略图/不重标
# ══════════════════════════════════════════════════════════════════════════════
def L1_materials():
    from orchestrator import bitable, feishu_io
    from orchestrator.bitable import MaterialFields as MF, MaterialStatus as MS
    section("L1", "素材入库(真库读素材表)")
    mats = feishu_io.list_records(MF.TABLE)
    ck("L1", f"素材表有货({len(mats)} 条)", len(mats) > 0)

    shot = [m for m in mats if bitable.text(m["fields"].get(MF.SHOT_STATUS)) == MS.SHOT]
    ck("L1", f"已拍素材 {len(shot)} 条(出稿的原料)", len(shot) > 0)

    # 打标质量:已拍素材必须有『备注』(豆包 vision 标)——它是文案的事实底座,空了文案只能编
    untagged = [bitable.text(m["fields"].get(MF.CODE)) for m in shot
                if not bitable.text(m["fields"].get(MF.NOTE)).strip()]
    ck("L1", "已拍素材都打过标(有『备注』=文案的事实底座,空了文案只能编)",
       not untagged, f"{len(untagged)} 条没标: {untagged[:5]}" if untagged else "")

    # 缩略图:运营在 base 里瞄一眼选材,没缩略图就得点开网盘
    nothumb = [bitable.text(m["fields"].get(MF.CODE)) for m in shot if not m["fields"].get(MF.THUMB)]
    ck("L1", "已拍素材有缩略图(base 里一眼能看)",
       len(nothumb) < len(shot) * 0.2, f"{len(nothumb)}/{len(shot)} 无缩略图")

    # 来源就低:AI 生成的必须标 AI(AI 声明门据此判,标错=替人误勾红线)
    srcs = {bitable.text(m["fields"].get(MF.SOURCE)) for m in mats}
    ck("L1", f"来源字段有值(AI声明门据此判):{sorted(s for s in srcs if s)}", any(srcs))

    # 编号唯一(重标会撞号)
    codes = [bitable.text(m["fields"].get(MF.CODE)) for m in mats if bitable.text(m["fields"].get(MF.CODE))]
    ck("L1", "素材编号无重复(重标会撞号)", len(codes) == len(set(codes)),
       f"重复: {[c for c in codes if codes.count(c) > 1][:3]}" if len(codes) != len(set(codes)) else "")


# ══════════════════════════════════════════════════════════════════════════════
# L2 找热点→灵感库。断言:去重/无标题过滤/正文落库(防搬运门要比对正文)
# ══════════════════════════════════════════════════════════════════════════════
def L2_trends():
    from orchestrator import bitable, feishu_io, trends
    from orchestrator.bitable import InspirationFields as IF
    section("L2", "找热点→灵感库(真库 + 真去重)")
    rows = feishu_io.list_records(IF.TABLE)
    ck("L2", f"灵感库可读({len(rows)} 条)", True)

    # 真跑去重:拿库里已有的标题再投一次,必须被去重掉(不是靠我说,是真跑)
    if rows:
        exist = bitable.text(rows[0]["fields"].get(IF.TITLE))
        res = trends.harvest_trends([{"标题": exist, "可借鉴": "压测重复投递", "源链接": "https://x"}],
                                    "巧荷", write=False)
        ck("L2", f"重复灵感真被去重(投「{exist[:12]}…」→ 新增 {len(res['新增'])} 条)",
           len(res["新增"]) == 0, f"去重失效: {res['新增']}")

    # 压测·坏数据:无标题 / 空对象 / 超长标题 → 不炸,且不落脏数据
    bad = [{"可借鉴": "没有标题"}, {}, {"标题": "观" * 2000, "可借鉴": "超长"}]
    try:
        res = trends.harvest_trends(bad, "巧荷", write=False)
        ck("L2", "坏数据(无标题/空对象/超长)不炸,无标题的被过滤",
           all(t for t in res["新增"]), f"落了空标题: {res['新增']}")
    except Exception as e:  # noqa: BLE001
        ck("L2", "坏数据不炸", False, f"炸了: {type(e).__name__}: {e}")

    # 2026-07-14 真跑证伪,这条检查以前在**传播一个错误的因果**:
    #   老话术:「防搬运门比对的是正文,没正文就形同虚设」——**假的**。
    #   `compose_prompt` 根本不收 source_text → 正文从没进过 prompt → LLM 没见过它 → 搬不了。
    #   门真正要守的是**LLM 眼睛看得见的**:灵感标题(=title_seed)+ 技能 few-shot 里的真实帖。
    # 所以这里该查的是**标题**(它才是真进 prompt 的那个),不是正文。
    # 正文降级为"锦上添花"(有凭证时能多一层保护),不是命门——非登录下小红书详情页只吐 452 字节空壳,
    # 拿它当硬门 = 把整条爆款模仿链路焊死在一个抓不到的东西上。
    with_title = [r for r in rows if bitable.text(r["fields"].get(IF.TITLE)).strip()]
    ck("L2", f"灵感带标题({len(with_title)}/{len(rows)} 条)——标题=title_seed,真进 prompt,防搬运门守它",
       not rows or len(with_title) == len(rows),
       "有灵感没标题 → 派不出活,且门少了一个比对源" if rows and len(with_title) < len(rows) else "")
    with_body = [r for r in rows if bitable.text(r["fields"].get(IF.BODY)).strip()]
    if rows and not with_body:
        print(f"      ↳ ℹ️ {len(rows)} 条灵感都没正文(非登录抓不到,详情页只吐空壳)。"
              f"**不影响出稿**:正文不进 prompt,LLM 没见过 → 搬不了。不算红。")


# ══════════════════════════════════════════════════════════════════════════════
# L3 派活:去重键真名/暂停号跳过/在途跳过
# ══════════════════════════════════════════════════════════════════════════════
def L3_dispatch():
    from orchestrator import dispatch
    section("L3", "派活 daily_dispatch(真库干跑)")
    rc, out = run(["python3", "-m", "scripts.daily_dispatch"])
    ck("L3", "daily_dispatch 真跑不崩", rc == 0, out[-200:] if rc else "")

    slots = dispatch._open_slots()
    empty = [s for s in slots if not s[0].strip()]
    ck("L3", f"在途去重键 {len(slots)} 个账号名全非空(空了=天天重复派活)", not empty, str(empty[:3]))

    rows = dispatch.dispatch("巧荷", write=False)
    ck("L3", f"派活出得来({len(rows)} 条 号×模式)", len(rows) > 0)
    noskill = [r for r in rows if not r.get("gen_skill")]
    ck("L3", "每条活都有 gen_skill(没技能=出不了稿)", not noskill, str(noskill[:2]))
    noneed = [r for r in rows if not r.get("material_needs")]
    ck("L3", "每条活都声明了素材需求(没需求=选不到素材=零素材废稿)", not noneed,
       str([r["account"] for r in noneed][:3]))


# ══════════════════════════════════════════════════════════════════════════════
# L4 出稿(真 LLM,真花钱):对味/配画面/篇幅达技能规格/不混制作说明/止于草稿待发
# ══════════════════════════════════════════════════════════════════════════════
def L4_draft(no_llm: bool):
    from orchestrator import accounts, bitable, draft, feishu_io
    from orchestrator.bitable import MaterialFields as MF, NoteStatus as NS
    section("L4", "出稿 draft_one(真 ARK,真花钱)")
    if no_llm:
        SKIP.append("L4 真出稿(--no-llm)")
        print("    ⊘ 跳过真出稿(--no-llm)")
        return

    combos = []
    for name, acc in sorted(accounts.load_all("巧荷").items()):
        for pb in acc.playbooks():
            combos.append((name, pb.get("content_type") or pb.get("id"), pb))

    total_cost = 0.0
    for name, ct, pb in combos:
        t0 = time.time()
        try:
            r = draft.generate_draft(name, "巧荷", llm_mode="real", content_type=ct,
                                     clothes="GY-001" if "品牌新作" in (ct or "") else "")
        except Exception as e:  # noqa: BLE001
            ck("L4", f"{name}/{ct} 真出稿", False, f"{type(e).__name__}: {str(e)[:120]}")
            continue
        total_cost += r["cost"]
        flags = r["quality_flags"]
        dt = time.time() - t0
        body = draft.body_text(r["draft_text"])
        mats = r.get("material_ids") or []
        print(f"    · {name}/{ct}  正文{len(body)}字  素材{len(mats)}条  {r['cost']}元  {dt:.0f}s")

        # 止于草稿待发 —— 红线:绝不自动发布、绝不代勾 AI 声明
        ck("L4", f"{name}/{ct} 止于『草稿待发』(红线:不自动发、不代勾AI声明)",
           r["note_fields"].get("状态") == NS.DRAFT_PENDING
           and "AI声明" not in r["note_fields"])
        # 制作说明绝不能混进要发的文案(运营从 base 复制就发)
        ck("L4", f"{name}/{ct} 文案不含制作说明(混进去=运营直接发到小红书)",
           not any("制作说明" in f for f in flags), str(flags))
        # 篇幅达技能自己的规格(有规格的模式)
        if pb.get("body_len"):
            ck("L4", f"{name}/{ct} 篇幅达技能规格 {pb['body_len']}(实际{len(body)}字)",
               not any("技能要求" in f for f in flags), str(flags))
        # 零素材 = 发不出去,必须被喊出来(不能"✅无问题"飘过去)
        if not mats:
            ck("L4", f"{name}/{ct} 零素材必须报警(小红书没图发不了)",
               any("零素材" in f for f in flags), f"零素材却没报: {flags}")

    print(f"    ⇒ 本轮真出稿总成本 {total_cost:.4f} 元({len(combos)} 条)")
    ck("L4", f"真出稿成本合理(<0.1元/条;曾是 3 元/条=claude -p 吞 33K 系统提示)",
       total_cost / max(1, len(combos)) < 0.1, f"均价 {total_cost/max(1,len(combos)):.4f} 元")


# ══════════════════════════════════════════════════════════════════════════════
# L5 审批 + L6 发布认领:AI声明门/控量门/货对板;认领写回状态+发布日
# ══════════════════════════════════════════════════════════════════════════════
def L5_L6_publish():
    from orchestrator import bitable, cockpit, feishu_io, guard
    from orchestrator.bitable import MaterialSource as MSrc, NoteFields as NF
    from orchestrator.guard import GuardError
    section("L5/L6", "审批 + 发布认领(真库 + 红线门真触发)")
    rc, out = run(["python3", "-m", "scripts.publish_ready"])
    ck("L5", "publish_ready 真跑不崩", rc == 0, out[-200:] if rc else "")

    # 压测·红线:含 AI 合成素材但没勾 AI 声明 → 门必须**真拒**(不是"应该会拒")
    try:
        guard.assert_ai_declared({NF.CODE: "压测稿"}, ai_required=True)
        ck("L5", "AI声明门真拒(含AI素材未勾声明→GuardError)", False, "门没拦住!红线破了")
    except GuardError:
        ck("L5", "AI声明门真拒(含AI素材未勾声明→GuardError)", True)

    # 全实拍则免勾(否则天天误报,人就不看了)
    # 2026-07-14:这两行原来写的是 `MSrc.SHOT` —— **MaterialSource 里根本没有 SHOT**(实拍是 REAL,
    # SHOT 是 MaterialStatus 的『已拍』)。一跑就 AttributeError,整个 L5 段当场崩。
    # 它没被发现,是因为**这个探针根本没人跑**(不在 review_gate、不在任何脚本里)——
    # 一个号称"17条链路综合验收"的东西,自己是死码,还崩着。**验收器自己没被验收过。**
    ck("L5", "全实拍素材免勾 AI 声明(不误报)",
       not guard.ai_declaration_required([MSrc.REAL, MSrc.REAL]))
    ck("L5", "含 AI 合成素材 → 需勾 AI 声明", guard.ai_declaration_required([MSrc.REAL, MSrc.AI]))

    # 压测·控量红线:超过单号日上限 → 门必须真拒
    from orchestrator import config
    try:
        guard.assert_publish_quota(config.PER_ACCOUNT_DAILY_PUBLISH + 1)
        ck("L5", f"控量门真拒(超单号日上限{config.PER_ACCOUNT_DAILY_PUBLISH}→GuardError)", False, "门没拦住!")
    except GuardError:
        ck("L5", f"控量门真拒(超单号日上限{config.PER_ACCOUNT_DAILY_PUBLISH}→GuardError)", True)
    try:
        guard.assert_publish_quota(0)
        ck("L5", "没到上限不误拦(0 条时放行)", True)
    except GuardError:
        ck("L5", "没到上限不误拦", False, "0 条也拦=控量误伤")

    # L6 认领:今日面板必须能列出『已发待回填链接』(没链接=回流没数据)
    p = cockpit.today_panel("巧荷")
    ck("L6", f"待回填链接可列({len(p['待回填链接'])} 条)——不回填=回流永远没数据", True)
    for n in p["待回填链接"]:
        ck("L6", f"待回填条目有账号名+深链(运营点开即达)「{n['title'][:14]}」",
           bool(n["account"].strip()) and bool(n.get("open")))


# ══════════════════════════════════════════════════════════════════════════════
# L7 回流 + L8 复盘
# ══════════════════════════════════════════════════════════════════════════════
def L7_L8_collect_report():
    from orchestrator import collect
    section("L7/L8", "回流采集 + 周报复盘(真库)")
    from orchestrator.bitable import NoteFields as _NF
    try:
        h = collect.harvestable_notes()
        ck("L7", f"harvestable_notes 真跑通({len(h)} 条可回流)", True)
        # 2026-07-14:这条检查以前是 `[n for n in h if not n.get("link")]` —— **恒假**。
        #   harvestable_notes 返回的是**原始 record**({record_id, fields}),里面根本没有 "link" 这个键,
        #   `n.get("link")` 永远是 None → 只要库里有一条可回流的稿,这道门就必红。
        #   而它红了也没人知道 —— 因为**这个探针当时没有任何人跑**。
        #   (同一种病第二次:上一次是飞书 search 的 link 字段形态。**别信形态,先真读一遍返回**。)
        # 更要命的是它问了个**自己保证了答案**的问题:harvestable_notes 最后一行就是 `if _link(...)` 过滤,
        #   返回的每条按构造都有链接。所以真正该验的不是"返回的有没有链接",而是**那个过滤器真的在滤**。
        bad_shape = [r for r in h if not collect._link(r["fields"].get(_NF.PUBLISH_LINK))]
        ck("L7", "可回流的都取到真 URL(dict 取 link,不取 text 描述)", not bad_shape,
           f"{len(bad_shape)} 条取不出 URL")
        # 真验那个过滤器:没填链接的『已发』必须被滤掉(否则采集器拿着空 URL 去采,必挂)。
        # 顺带守住"取 link 不取 text"——url 字段的 text 是描述文字,拿它去采必挂(这条踩过)。
        ck("L7", "没填链接的『已发』真被滤掉(不拿空URL去采)", not collect._link(None))
        ck("L7", "url 字段取 link 不取 text(取 text=拿到描述文字,真采必挂)",
           collect._link({"link": "https://a.com/x", "text": "我的第一篇笔记"}) == "https://a.com/x")
    except Exception as e:  # noqa: BLE001
        ck("L7", "harvestable_notes 真跑通", False, f"{type(e).__name__}: {str(e)[:120]}")

    rc, out = run(["python3", "-m", "scripts.collect_metrics"])
    ck("L7", "collect_metrics 真跑不崩(没数据也不崩)", rc == 0, out[-200:] if rc else "")

    rc, out = run(["python3", "-m", "scripts.weekly_report"])
    ck("L8", "weekly_report 真跑不崩(无数据不崩=压测边界)", rc == 0, out[-200:] if rc else "")


# ══════════════════════════════════════════════════════════════════════════════
# L0/L9 人面(运营真正用的):今日卡片 + 驾驶舱 + 周排期
# ══════════════════════════════════════════════════════════════════════════════
def L0_L9_cockpit():
    from orchestrator import cockpit
    section("L0/L9", "人面:今日卡片 + 驾驶舱 + 周排期(运营不敲终端,这层不过=系统不可用)")
    p = cockpit.today_panel("巧荷")
    active = p["待审"] + p["待发"]
    empty = [n["title"] for n in active if not n["account"].strip()]
    ck("L9", f"待审/待发 {len(active)} 条账号名全非空(空了运营不知道是哪个号)", not empty, str(empty[:3]))
    noopen = [n["title"] for n in active if not n.get("open")]
    ck("L9", "每条都有深链(点开即达 base 那一行)", not noopen, str(noopen[:3]))

    card = cockpit.today_card("巧荷", panel=p)
    heads = [el.get("text", {}).get("content", "") for el in card["elements"]]
    bad = [h for h in heads if h.startswith("**") and h.split("\n")[0].strip("* ") in ("", "·")]
    ck("L0", "卡片按真账号名分组(无空表头——运营手机上一眼知道是哪个号)", not bad, str(bad[:2]))
    ck("L0", "卡片有内容(不是空卡)", len(card["elements"]) >= 1)

    w = cockpit.weekly_schedule("巧荷")
    allnotes = [n for d in w["days"] for n in d["notes"]] + w["逾期"] + w["未排期"]
    emptyw = [n["title"] for n in allnotes if not n["account"].strip()]
    ck("L9", f"周排期 {len(allnotes)} 条账号名全非空", not emptyw, str(emptyw[:3]))


# ══════════════════════════════════════════════════════════════════════════════
# L10 拍摄单 + L11 成本
# ══════════════════════════════════════════════════════════════════════════════
def L10_L11_shot_cost():
    from orchestrator import config, cost, shotlist
    section("L10/L11", "拍摄需求单 + 成本预算(真库)")
    gaps = shotlist.shot_needs("巧荷")
    ck("L10", f"补拍单出得来({len(gaps)} 项缺口)", True)
    for g in gaps:
        ck("L10", f"缺口有账号+类型+投递去向(人照着就能去拍)「{g['account']}/{g['类型']}」",
           bool(g["account"].strip()) and bool(g.get("类型")) and bool(g.get("投递去向")))

    c = cost.monthly_cost_cny()
    ck("L11", f"当月成本聚合得出来({c} 元 / 预算 {config.BUDGET_MONTHLY_CNY} 元)", isinstance(c, (int, float)))
    warn = cost.budget_alert()
    ck("L11", f"预算告警逻辑可跑({'已触发: ' + warn[:40] if warn else '未超阈,不误报'})", True)


# ══════════════════════════════════════════════════════════════════════════════
# L12 红线闸(压测·穿透):写生产库必须**物理到不了**;防搬运门必须真拦逐字搬
# ══════════════════════════════════════════════════════════════════════════════
def L12_redlines():
    from orchestrator import config, guard
    from orchestrator.guard import GuardError
    section("L12", "红线闸(压测·穿透:真拿生产库 token 去撞门)")

    # 穿透 ①:TEST_MODE 下把 Base 换成生产库 → 三条写路径都必须被 guard 物理拦死
    try:
        guard.assert_base_allowed(config.PROD_BASE, True)
        ck("L12", "Base 守卫真拒生产库(TEST_MODE 下拿生产 token 撞门)", False,
           "❌❌ 红线破了!能写生产库!")
    except GuardError:
        ck("L12", "Base 守卫真拒生产库(拿生产 token 撞门→GuardError)", True)

    # 空 token 也拒(别静默写到不知道哪去)
    try:
        guard.assert_base_allowed("", True)
        ck("L12", "空 Base token 被拒", False, "空 token 放行=不知道写哪去了")
    except GuardError:
        ck("L12", "空 Base token 被拒", True)

    # 测试库放行(否则什么都干不了)
    try:
        guard.assert_base_allowed(config.TEST_BASE, True)
        ck("L12", "测试库放行(不误伤)", True)
    except GuardError as e:
        ck("L12", "测试库放行(不误伤)", False, str(e)[:80])

    # 穿透 ②:防搬运门 —— 拿一段"对标源正文"逐字搬进产出,门必须真拒
    src = "夏天最好的时刻,是风比人先进门。这一身不必急着解释,光落上去它自己会说话。"
    try:
        guard.assert_no_source_leak(src, f"OOTD｜压测\n\n{src}\n\n#汉服")
        ck("L12", "防搬运门真拒逐字搬(爆款只当情报,不搬原文)", False, "❌ 逐字搬过门了!")
    except GuardError:
        ck("L12", "防搬运门真拒逐字搬(爆款只当情报,不搬原文)", True)

    # 不误伤:自己写的稿(不含源片段)必须放行
    try:
        guard.assert_no_source_leak(src, "OOTD｜粉罗载光,细闪沾衣\n\n光落在衣上,风把影子摇醒。\n\n#汉服")
        ck("L12", "防搬运门不误伤原创稿", True)
    except GuardError as e:
        ck("L12", "防搬运门不误伤原创稿", False, f"误杀了: {str(e)[:80]}")


# ══════════════════════════════════════════════════════════════════════════════
# L13 schema 契约 + L14 数据安全 + L15 运维巡检
# ══════════════════════════════════════════════════════════════════════════════
def L13_L14_L15_ops():
    section("L13/L14/L15", "schema契约 + 数据安全 + 运维巡检(真跑 CLI)")
    rc, out = run(["python3", "scripts/check_schema_drift.py"])
    ck("L13", "活 schema 漂移探针绿(代码词汇 ⊆ 活库)", rc == 0, out[-200:] if rc else "")

    rc, out = run(["python3", "scripts/backup_tables.py"], timeout=300)
    ck("L14", "备份真跑通(误删可恢复的前提)", rc == 0, out[-160:] if rc else "")

    rc, out = run(["python3", "scripts/cron_status.py"])
    ck("L15", "cron_status 真跑不崩(运维看得到上线态)", rc == 0, out[-160:] if rc else "")


# ══════════════════════════════════════════════════════════════════════════════
# L16 加工环(gated,默认关)+ L17 技能层(唯一真源)
# ══════════════════════════════════════════════════════════════════════════════
def L16_L17_skills():
    from orchestrator import accounts, config, draft, processing
    section("L16/L17", "加工环(gated) + 技能层(唯一真源)")

    ck("L16", "加工环默认关(GY_PROCESSING_ENABLED 未开 → maybe_process 原样返回)",
       not config.PROCESSING_ENABLED)
    ids = ["recA", "recB"]
    out = processing.maybe_process(list(ids), account="ootd号", mode="视频唯美OOTD",
                                   clothes="", decide=None, execute=None)
    ck("L16", "关态下 maybe_process 是 no-op(不偷偷改素材)", out == ids, f"{ids} → {out}")

    # L17 技能唯一真源:全号全模式的 gen_skill 都必须从 skills/ 载得到
    for name, acc in sorted(accounts.load_all("巧荷").items()):
        for pb in acc.playbooks():
            gs = accounts.gen_skill_of(pb)
            # load_gen_skill 现在装不上就抛(不再静默返 "")。探针的职责是**报红**,不是跟着炸——
            # 接住它,把"技能装不上"如实渲染成一条红检查,人才看得见是哪个号哪个模式。
            try:
                txt = draft.load_gen_skill(gs)
            except draft.SkillMissing as e:
                txt = ""
                print(f"      ↳ {str(e)[:88]}")
            ck("L17", f"{name}/{pb.get('content_type')} 的技能「{gs}」载得到({len(txt)}字符)", bool(txt))

    # workspace 不许再藏技能(local-skills 是双源遮蔽的入口)
    ck("L17", "workspace 不藏技能(无 local-skills/ → 唯一真源=qiaohe-skill 仓)",
       not (ROOT / "local-skills").exists())


# ══════════════════════════════════════════════════════════════════════════════
# 压测·坏数据边界:空账号/无素材/坏字段/超长 → 降级可读,不崩
# ══════════════════════════════════════════════════════════════════════════════
def STRESS_bad_data():
    from orchestrator import cockpit, draft
    section("压测", "坏数据边界(空/缺字段/超长/坏形态 → 降级不崩)")

    # 笔记记录缺一切字段 → 分桶不炸
    try:
        from datetime import date
        v = cockpit._bucket_schedule([{"record_id": "recX", "fields": {}}], date.today())
        ck("压测", "笔记缺全部字段 → 周排期分桶不炸(降级)", isinstance(v, dict))
    except Exception as e:  # noqa: BLE001
        ck("压测", "笔记缺全部字段 → 周排期分桶不炸", False, f"{type(e).__name__}: {e}")

    # 素材字段是坏形态(link 给字符串 / 数字给 None)→ 选材不炸
    try:
        bad = [{"record_id": "recBad", "fields": {"类型": "上身图", "拍摄状态": "已拍",
                                                  "适用账号": "不是link是字符串",
                                                  "笔记表-关联素材": None}}]
        got = draft._material_hits(bad, ["上身图"])
        ck("压测", "素材坏形态(link给字符串/None)→ 选材不炸", isinstance(got, list))
    except Exception as e:  # noqa: BLE001
        ck("压测", "素材坏形态 → 选材不炸", False, f"{type(e).__name__}: {e}")

    # 超长标题种子 → 出稿不炸(stub,零成本)
    try:
        r = draft.generate_draft("ootd号", llm_mode="stub", title_seed="观" * 5000, material_rows=[])
        ck("压测", "超长标题种子(5000字)→ 出稿不炸", bool(r["title"]))
    except Exception as e:  # noqa: BLE001
        ck("压测", "超长标题种子 → 出稿不炸", False, f"{type(e).__name__}: {e}")

    # 空稿 / 无标签 → 质检报出来而不是静默通过
    flags = draft.quality_flags("", {})
    ck("压测", "空稿被质检抓住(不静默通过)", flags == ["空稿"], str(flags))


# ══════════════════════════════════════════════════════════════════════════════
LINKS = {
    "L1": L1_materials, "L2": L2_trends, "L3": L3_dispatch,
    "L5": L5_L6_publish, "L7": L7_L8_collect_report, "L9": L0_L9_cockpit,
    "L10": L10_L11_shot_cost, "L12": L12_redlines, "L13": L13_L14_L15_ops,
    "L16": L16_L17_skills, "STRESS": STRESS_bad_data,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="跳过 L4 真出稿(省钱;但文案质量就没验)")
    ap.add_argument("--only", default="", help="只跑指定链路,逗号分隔(如 L4,L12)")
    a = ap.parse_args()

    from orchestrator import config
    print("═" * 66)
    print(f"  全链路真跑压测台  env={config.ENV_NAME}  base={config.BASE_TOKEN[:12]}…")
    print("  真库 / 真 ARK / 真 lark-cli —— 绝不自动发布、不代勾 AI 声明、不碰生产库")
    print("═" * 66)

    only = {s.strip().upper() for s in a.only.split(",") if s.strip()}
    t0 = time.time()

    if not only or "L4" in only:
        try:
            L4_draft(a.no_llm)
        except Exception:  # noqa: BLE001
            FAIL.append("L4 崩了")
            traceback.print_exc()

    for key, fn in LINKS.items():
        if only and key not in only:
            continue
        try:
            fn()
        except Exception:  # noqa: BLE001
            FAIL.append(f"{key} 崩了")
            traceback.print_exc()

    dt = time.time() - t0
    print("\n" + "═" * 66)
    if SKIP:
        print(f"  ⊘ 跳过: {', '.join(SKIP)}")
    if FAIL:
        print(f"  ❌ 全链路压测**未通过** —— {len(FAIL)} 项真事不成立({dt:.0f}s):")
        for f in FAIL:
            print(f"     · {f}")
        print("═" * 66)
        return 1
    print(f"  ✅ 全链路压测通过 —— 每条链路真跑、每条红线真触发过({dt:.0f}s)")
    print("═" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
