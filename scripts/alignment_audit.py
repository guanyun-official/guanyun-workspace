#!/usr/bin/env python3
"""全体系对齐审查(硬门)—— 把"人想起来方便的逻辑,落实下来是 bug"这个病机械化成一个退出码。

**为什么存在**:2026-07-14 一整天,每一轮"审查"都还能找出新问题——因为审查是**手工的**:
凭记性和运气翻一遍,当然翻不完。要终结,审查本身必须变成一道**每次都跑、返回 0 才算过**的门。

这一整轮抓到的 bug,归纳下来只有 7 种形态,全都可以机械检测:

  ① 死码      —— 门/函数造好了,生产代码零调用(assert_publish_quota 曾是死码,只在卡片上"给人看")
  ② 死配置    —— config 项定义了没人读(GY_METRICS_MODE:运维设了 real,实际跑的还是 stub 假数据)
  ③ 空壳/名不副实 —— base 视图名字承诺了分组/筛选,实际什么都没配(「按颜色分组」没有分组)
  ④ 数据支撑不了 —— 视图/功能依赖表里根本不存在的字段(素材表没有『颜色』列,却建了「按颜色分组」)
  ⑤ 默认值陷阱 —— 函数有默认值,而**所有调用点都不传** → "忘了传"变成"静默记错"
                  (log_run(table="笔记表") 9 个调用点全不传 → 日志写着"打标在操作笔记表",它在撒谎)
  ⑥ 空门      —— 门的逻辑是对的,但它比对的**数据在真库里永远是空的**
                  (防搬运门比对灵感正文,而灵感库『文案』全空 → 整段逐字搬也能过。**最危险的一种:
                   不是没做,是做了、看着像在保护你、实际是空的**)
  ⑦ 假形态 mock —— 测试固件用真实世界不存在的形态(裸字符串 "ootd号"),而真 search API 回
                  {link_record_ids: [...]} → **测试常绿、生产照坏,测试就是站在窟窿前守着的那个人**

任一条不过 → 非 0 退出。这是门,不是报告。

  python3 scripts/alignment_audit.py          # 全查(含真库:视图/字段/门的输入)
  python3 scripts/alignment_audit.py --offline # 只查代码(死码/死配置/默认值陷阱/假形态),不触网
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL: list[str] = []

# ══════════════════════════════════════════════════════════════════════════════
# 死码白名单 —— **必须写明理由**。规矩是"要么真做出来,要么删掉";留着的必须说清为什么。
# 静默豁免 = 又一个"看着像在保护你、实际是空的"。
# ══════════════════════════════════════════════════════════════════════════════
DEAD_CODE_ALLOW = {
    "publish.approve":
        "ADR-0005 卡片按钮动作函数。**运营现在是在 base 里直接改状态**(不点卡片按钮),"
        "所以生产零调用是**符合现状**的。等服务器 webhook 接上、卡片真有按钮时才会被调用。"
        "**注意**:它不是死码,是**待接线**——webhook 一天没接,卡片就一天不该出现'点按钮'的字样。",
    "publish.fill_publish_link":
        "同上(ADR-0005 聊天动作函数:运营把链接发给 bot → webhook → 认领)。webhook 未接 → 运营够不着它。"
        "**后果已用 publish.stamp_published_at() 兜住**:运营在 base 只能改状态+填链接,"
        "『实际发布日』他做不了 → 系统在 publish_ready(cron)里自愈补上,控量红线不再形同虚设。",
    "compose.simple_decide":
        "ADR-0006 加工环的 gated 钩子(GY_PROCESSING_ENABLED 默认关)。**关态下 processing.maybe_process "
        "原样返回、绝不调它** —— 这是设计,不是遗漏。开关一开就会被调。",
    "compose.compose_execute": "同上(ADR-0006 加工环 gated 钩子)。",
}


def bad(kind: str, what: str, why: str = "") -> None:
    FAIL.append(f"[{kind}] {what}" + (f" —— {why}" if why else ""))
    print(f"  ✗ {what}" + (f"\n      {why}" if why else ""))


def ok(what: str) -> None:
    print(f"  ✓ {what}")


def _pysrc(*dirs: str) -> dict[Path, str]:
    out = {}
    for d in dirs:
        for p in (ROOT / d).rglob("*.py"):
            if "__pycache__" in str(p):
                continue
            out[p] = p.read_text(encoding="utf-8")
    return out


def _real_callers(fn: str) -> int:
    """**真调用点**数量(AST 数 ast.Call;注释/docstring 里出现的名字不算)。

    2026-07-14 —— 这个函数的来历,就是这个审查器要抓的病,**我自己连犯三次**:
      1. 第一版「假承诺」检查用 regex 数源码里 `fn(` 出现次数 >1 就当"接线了"。
         而 publish.py 的注释和 docstring **反复提到 fill_publish_link()** → 被算成已接线
         → 检查当场变成摆设(把假承诺塞回卡片,它一声不吭)。**注释把检查骗了。**
      2. 改用 AST 后,我把这个 helper **插错了位置,根本没插进文件**,而且没验证就往下走。
      3. 于是它成了最恶劣的一种空壳:`_real_callers` 只在"真要检查"时才被调用 ——
         **卡片没问题时循环体不执行 → 不崩、绿灯;卡片真有假承诺时才执行 → 崩溃。**
         **它平时永远是绿的,只在真该报警的那一刻炸掉。**

    教训写死在这:**检查器自己也必须过"把 bug 塞回去,看它报不报"这一关**,
    否则它就是下一个"看着像在保护你、实际是空的"东西。
    """
    n = 0
    for _q, src in _pysrc("orchestrator", "scripts").items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name == fn:
                    n += 1
    return n


# ══════════════════════════════════════════════════════════════════════════════
# ① 死码:orchestrator 的 public 函数,生产代码零调用
#    (测试调用**不算数**——assert_publish_quota 曾经就只有测试在调,而门从没装在门框上)
# ══════════════════════════════════════════════════════════════════════════════
def audit_dead_code() -> None:
    print("\n── ① 死码(造好了没装在门框上)" + "─" * 34)
    prod = _pysrc("orchestrator", "scripts")
    tests = _pysrc("tests")
    tsrc = "\n".join(tests.values())
    found = 0
    for p, s in prod.items():
        if "orchestrator/" not in str(p):
            continue
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            fn = node.name
            callers = sum(len(re.findall(rf"\b{fn}\s*\(", src))
                          for q, src in prod.items() if q != p)
            selfuse = len(re.findall(rf"\b{fn}\s*\(", s)) - 1     # 减去 def 本身
            if callers == 0 and selfuse == 0:
                key = f"{p.stem}.{fn}"
                if key in DEAD_CODE_ALLOW:
                    ok(f"{key}() 生产零调用 —— **白名单(有理由)**:{DEAD_CODE_ALLOW[key][:52]}…")
                    continue
                in_tests = len(re.findall(rf"\b{fn}\s*\(", tsrc))
                tag = (f"**只有测试在调它({in_tests} 次)= 测试在给死码站台**"
                       if in_tests else "连测试都没有")
                bad("死码", f"{p.relative_to(ROOT)}::{fn}()", f"生产代码零调用;{tag}")
                found += 1
    if not found:
        ok("orchestrator 的 public 函数都被生产代码真调用了")


# ══════════════════════════════════════════════════════════════════════════════
# ② 死配置:config 里定义了,没人读
#    (GY_METRICS_MODE 曾是死配置:运维在 .env 设了 real,collect_metrics 写死不读它 → 跑的还是 stub)
# ══════════════════════════════════════════════════════════════════════════════
def audit_dead_config() -> None:
    print("\n── ② 死配置(设了没人读,人以为生效了)" + "─" * 26)
    cfg_path = ROOT / "orchestrator/config.py"
    cfg = cfg_path.read_text(encoding="utf-8")
    others = {p: s for p, s in _pysrc("orchestrator", "scripts").items() if p != cfg_path}
    found = 0
    for m in re.finditer(r"^([A-Z][A-Z0-9_]+)\s*=", cfg, re.M):
        name = m.group(1)
        # 别的文件读了吗
        outside = any(re.search(rf"\b{name}\b", s) for s in others.values())
        # config.py 内部被别的函数用了吗(TENANT_HOST 就是被 record_url 用的——
        # 早期审查脚本把 config.py 排除在外,误报它是死配置。**扫描工具自己也会撒谎**)
        body = cfg[m.end():]
        inside = bool(re.search(rf"\b{name}\b", cfg[:m.start()] + body))
        if not outside and not inside:
            bad("死配置", f"config.{name}", "定义了,全仓没人读 —— 人照着注释设了 env,以为生效,其实没有")
            found += 1
    if not found:
        ok("每个 config 项都真的被读")


# ══════════════════════════════════════════════════════════════════════════════
# ⑤ 默认值陷阱:关键参数有默认值,而**所有调用点都不传** → "忘了传"变成"静默记错"
#    (log_run(table="笔记表") 9 个调用点全不传 → 日志写着"打标在操作笔记表",它在撒谎)
# ══════════════════════════════════════════════════════════════════════════════
WATCH_DEFAULTS = [("log_run", "table"), ("collect", "mode"), ("harvest_trends", "write")]


def audit_default_traps() -> None:
    print("\n── ⑤ 默认值陷阱(所有调用点都不传 → 静默走默认)" + "─" * 16)
    prod = _pysrc("orchestrator", "scripts")
    found = 0
    for fn, param in WATCH_DEFAULTS:
        has_default = False
        for p, s in prod.items():
            m = re.search(rf"def {fn}\((.*?)\)\s*->", s, re.S)
            if m and re.search(rf"\b{param}\s*[:=][^,)]*=", m.group(1)):
                has_default = True
        if not has_default:
            continue
        callers = passed = 0
        for p, s in prod.items():
            for c in re.finditer(rf"{fn}\((.*?)\)", s, re.S):
                if f"def {fn}" in s[max(0, c.start() - 12):c.start()]:
                    continue
                callers += 1
                if f"{param}=" in c.group(1):
                    passed += 1
        if callers and passed == 0:
            bad("默认值陷阱", f"{fn}(…, {param}=<默认>)",
                f"{callers} 个调用点**没有一个传 {param}** → 全部静默走默认值。"
                f"默认值把'忘了传'变成'静默记错'——去掉默认值,逼调用点说清楚")
            found += 1
    if not found:
        ok("被盯的关键参数没有'全员走默认值'的")


# ══════════════════════════════════════════════════════════════════════════════
# ⑦ 假形态 mock:测试固件用真实世界不存在的形态
#    真 search API 回 {link_record_ids:[...]};测试里写裸字符串 "ootd号" → 测试常绿、生产照坏
# ══════════════════════════════════════════════════════════════════════════════
LINK_FIELDS = ["账号", "内容类型", "关联素材", "适用账号", "笔记表-关联素材", "转化为笔记"]


def audit_fake_fixtures() -> None:
    print("\n── ⑦ 假形态 mock(测试固件是真实世界不存在的形态)" + "─" * 14)
    found = 0
    for p, s in _pysrc("tests").items():
        for lf in LINK_FIELDS:
            # link 字段被赋成**裸字符串** → 真 API 从不返回这种形态
            for m in re.finditer(rf'["\']{re.escape(lf)}["\']\s*:\s*["\']([^"\']+)["\']', s):
                line = s[:m.start()].count("\n") + 1
                bad("假形态mock", f"{p.relative_to(ROOT)}:{line}  「{lf}」= 裸字符串 {m.group(1)!r}",
                    "真 search API 回的是 {'link_record_ids': [...]}(无 text),list/get 回 "
                    "[{'record_ids':[...], 'text':'名'}] —— **裸字符串是真实世界不存在的形态**。"
                    "假 mock 比真数据干净 → 测试常绿、生产照坏")
                found += 1
    if not found:
        ok("测试固件里的 link 字段都是真形态")


# ══════════════════════════════════════════════════════════════════════════════
# ③④ base 视图:空壳 / 名不副实 / 依赖不存在的字段(真库)
# ══════════════════════════════════════════════════════════════════════════════
def _cli(*args) -> dict:
    from orchestrator import config
    r = subprocess.run(["lark-cli", *args, "--as", "bot", "--base-token", config.BASE_TOKEN],
                       capture_output=True, text=True,
                       env={**os.environ, "LARK_CLI_NO_PROXY": "1"}, timeout=60)
    raw = r.stdout or r.stderr
    return json.loads(raw[raw.find("{"):]) if "{" in raw else {}


DEFAULT_VIEW_NAMES = {"Grid View", "表格"}


def audit_views() -> None:
    print("\n── ③④ base 视图(空壳 / 名不副实 / 依赖不存在的字段)" + "─" * 10)
    found = 0
    for t in [x["name"] for x in _cli("base", "+table-list")["data"]["tables"]]:
        fields = {f["id"]: f["name"] for f in _cli("base", "+field-list", "--table-id", t)["data"]["fields"]}
        names = set(fields.values())
        for v in _cli("base", "+view-list", "--table-id", t)["data"]["views"]:
            d = _cli("base", "+view-get", "--table-id", t, "--view-id", v["id"])["data"]["view"]
            m = d.get("_meta") or {}
            grp = [fields.get(g, g) for g in (m.get("group") or [])]
            flt, srt = m.get("filter"), (m.get("sort") or [])
            name = d.get("name", "")
            if name in DEFAULT_VIEW_NAMES:
                continue
            if not grp and not flt and not srt:
                bad("空壳视图", f"{t}「{name}」",
                    "无分组/无筛选/无排序 —— 名字承诺了什么,实际什么都没配。"
                    "**建的时候人想起来方便,功能从没做过**")
                found += 1
                continue
            # 名不副实:名字说"按X",实际分组的不是 X
            m2 = re.match(r"按(.+?)(分组|看|$)", name)
            if m2 and grp:
                claim = m2.group(1).strip()
                if claim not in names:
                    bad("数据支撑不了", f"{t}「{name}」",
                        f"名字承诺按『{claim}』,但**表里根本没有这一列**(有的是:{sorted(names)[:6]}…)"
                        f" —— 永远做不出来,别留着骗人")
                    found += 1
                elif not any(claim in g for g in grp):
                    bad("名不副实", f"{t}「{name}」",
                        f"名字说按『{claim}』,**实际按『{'/'.join(grp)}』分组** —— 名字在骗人")
                    found += 1
    if not found:
        ok("所有视图名实相符,且都真配了分组/筛选/排序")


# ══════════════════════════════════════════════════════════════════════════════
# ⑥ 空门:门的逻辑是对的,但它比对的数据在真库里**永远是空的**
#    (防搬运门比对灵感正文,而灵感库『文案』全空 → 整段逐字搬也能过。**最危险的一种**)
# ══════════════════════════════════════════════════════════════════════════════
GATE_INPUTS = [
    # (门, 它依赖的表, 依赖的字段, 全空时的后果)
    ("防搬运门 assert_no_source_leak", "灵感库", "文案",
     "门比对的是原帖正文。全空 → 门无从比对 → **整段逐字搬也能过**(现已 fail-closed:"
     "声称蹭爆款却无正文=直接拒;但源头仍该补正文,否则爆款模仿这条链路整个走不通)"),
    ("AI声明门 assert_ai_declared", "素材表", "来源",
     "门按素材『来源』判要不要勾 AI 声明。全空 → 一律判成不需要 → **AI 内容漏标**(合规硬伤)"),
]


def audit_empty_gates() -> None:
    print("\n── ⑥ 空门(门是对的,但它比对的数据永远是空的)" + "─" * 16)
    from orchestrator import bitable, feishu_io
    found = 0
    for gate, table, field, why in GATE_INPUTS:
        try:
            rows = feishu_io.list_records(table)
        except Exception as e:  # noqa: BLE001
            bad("空门", f"{gate} ← {table}.{field}", f"读不到该表:{str(e)[:60]}")
            found += 1
            continue
        if not rows:
            # **空表不等于门是好的** —— 只是还没有东西可拦。如实说,别静默通过(那是自欺)。
            print(f"  ○ {gate} ← {table} **是空的**(0 行)—— 门没东西可拦,"
                  f"说明**喂它的那条链路还没真跑过**。不算红,但也别当绿。")
            continue
        filled = sum(1 for r in rows if bitable.text(r["fields"].get(field)).strip())
        if filled == 0:
            bad("空门", f"{gate} ← 依赖 {table}.『{field}』,而它在真库里 0/{len(rows)} 有值", why)
            found += 1
        else:
            ok(f"{gate} ← {table}.『{field}』 {filled}/{len(rows)} 有值(门有东西可比)")
    if not found:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# ⑧ 人面产物没人以人的眼睛看过 —— **这轮 bug 最大的来源,而且机器最难查**
#
#    实例(全是绿门/单测/schema 一条都抓不到的):
#      · 卡片待审区堆 5 条几乎一样的稿 —— 人打开第一反应"我审哪条?"
#      · 「今日 4/3 已达上限」—— 可他今天一条都没发,那 4 是排队数。**数字没错,话在骗人**
#      · 批了的稿被门拦下 → 停在『已批准』→ **在任何人面视图里都不出现** = 黑洞
#      · 补拍单让摄影师去打开 `skills/writing-ootd-caption/SKILL.md` —— 他在片场,打不开也不该打开
#      · 周报用 0 赞的数据说「本周最有效,可加权多产这类」
#      · 卡片说「去 base 关联素材」—— **这是错的建议**:文案是没看过素材写的,挂图会货不对板
#
#    机器能查的那部分,查死;查不了的部分,由 loop 强制"每轮真渲染 + 以人的眼睛读一遍"。
# ══════════════════════════════════════════════════════════════════════════════
# **给 agent 看的东西,不许出现在人面产物里**。三类,一个都不许:
#   · 代码库路径/技能名  —— 摄影师在片场,打不开也不该打开 SKILL.md
#   · **环境变量名**     —— 2026-07-14 人眼审现场抓到:我上一轮刚从补拍单里删掉 SKILL.md 路径,
#                          转头就在**周报**里塞了句"要真拿数据得 `GY_METRICS_MODE=real`"。
#                          运营在手机上收到周报,看到一串环境变量 —— 他不敲终端,这句话对他毫无意义,
#                          而且**这件事根本不是他能做的**(改环境变量是部署侧的事)。
#                          审查器当时没抓到,因为 AGENT_ONLY 里没有"环境变量名"这个模式。
#   · record_id/field_id —— 内部主键,人看不懂
AGENT_ONLY = [
    ("SKILL.md", "代码库文件"), ("skills/", "代码库路径"), ("brands/", "代码库路径"),
    ("orchestrator/", "代码库路径"), ("scripts/", "代码库路径"),
    (r"\bGY_[A-Z0-9_]{3,}", "**环境变量名**(改它是部署侧的事,不是运营能做的)"),
    (r"\b[A-Z][A-Z0-9_]{5,}=[a-z]", "**环境变量赋值**(给运维/agent 看的,不是给人的)"),
    ("record_id", "内部主键"), (r"\brec\w{10,}", "内部主键"),
    (r"\bfld\w{8,}", "内部字段ID"), (r"\btbl\w{10,}", "内部表ID"),
    ("playbook_id", "内部标识"), ("gen_skill", "内部技能名"),
]


def _scan_agent_only(surface: str, text: str, reader: str) -> int:
    """人面产物里扫"给 agent 看的东西"。surface=产物名,reader=它的读者是谁。

    **先剥掉 URL 再扫**(2026-07-14 我自己踩的假阳性):第一版直接扫全文,把 base 深链里的
    `?table=tblsice…&record=recvphd…` 抓成"给错读者"——**可那正是运营点标题直达 base 那一行的机制**:
    record_id 藏在可点链接里,人根本看不见,更不需要看懂。这不是给错读者,是正常深链。
    **假阳性比漏报更毒**:检查每次都红 → 人开始无视它(狼来了)→ 这道门就废了。
    所以:URL **里面**的内部 ID 放行;URL **外面**的(以及任何地方的代码路径/环境变量)一律不许。
    """
    naked = re.sub(r"https?://\S+", "«链接»", text)      # 深链整段替掉:里面的 id 是机制,不是给人读的
    n = 0
    for pat, why in AGENT_ONLY:
        m = re.search(pat, naked)
        if m:
            bad("人面·给错读者", f"{surface}里出现「{m.group(0)}」",
                f"{why}。**{surface}的读者是{reader}** —— 给错读者 = 让人白费功夫,或干脆看不懂")
            n += 1
    return n


def audit_human_surface() -> None:
    print("\n── ⑧ 人面产物(以人的眼睛看,合不合理)" + "─" * 22)
    from orchestrator import bitable, cockpit, feishu_io, report, shotlist
    from orchestrator.bitable import NoteFields as NF
    found = 0

    p = cockpit.today_panel("巧荷")
    card = cockpit.today_card("巧荷", panel=p)
    blob = json.dumps(card, ensure_ascii=False)
    needs = shotlist.shot_needs("巧荷")

    # (a)(b) **三个人面产物全扫**(之前只扫了卡片和补拍单,**漏了周报** —— 环境变量就是从那儿漏出去的)
    found += _scan_agent_only("今日卡片", blob, "运营(手机上,不敲终端)")
    for g in needs:
        found += _scan_agent_only("补拍单", f"{g.get('拍摄要求','')} {g.get('参考','')} "
                                            f"{g.get('投递去向','')}", "摄影师(在片场)")
    wk_txt = report.format_weekly(report.weekly_summary(
        [r["fields"] for r in feishu_io.list_records(NF.TABLE)], needs=needs))
    found += _scan_agent_only("周报", wk_txt, "运营(周一看,不敲终端)")

    # (c) 黑洞:某个在途状态的稿,在**任何**人面视图里都不出现 → 人以为它发出去了
    surfaced = {n["title"] for k in ("待审", "待发", "待回填链接", "已暂停", "卡住") for n in p.get(k, [])}
    for st in ("草稿待发", "已批准", "待发布"):
        for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [st]):
            title = bitable.text(r["fields"].get(NF.TITLE))
            if title and title not in surfaced:
                bad("人面·黑洞", f"「{title}」(状态={st})不在任何人面视图里",
                    "人在卡片/面板上看不到它 → 以为它发出去了。**门拦住 ≠ 事情办完**:"
                    "拦住 + 说清为什么 + 给出路,才算数")
                found += 1

    # (d) 卡片分组表头不许为空(link 形态坑直接砸这:账号名读空 → 人不知道是哪个号)
    for el in card["elements"]:
        c = (el.get("text") or {}).get("content", "")
        head = c.split("\n")[0].strip("* ")
        if c.startswith("**") and head in ("", "·"):
            bad("人面·空表头", "今日卡片有空的账号分组表头",
                "运营一眼看不出这是哪个号。link 字段从 search 只回 id、没有 text —— 这坑直接砸在人脸上")
            found += 1

    # (e) 话不许说一半(手机上读到「…只当意境里一个词轻点,不」)
    for g in shotlist.shot_needs("巧荷"):
        for k in ("拍摄要求", "参考"):
            s = (g.get(k) or "").strip()
            if s and s[-1] in "不的了和与或在把被将而且但":
                bad("人面·话说一半", f"补拍单『{k}』断在半句:…{s[-12:]}",
                    "硬截字数会断在半个词上,人读着一头雾水。要在句子边界断")
                found += 1

    # (f) 零数据不许编结论(周报曾用 0 赞的稿说「本周最有效,可加权多产这类」)。复用上面已算的 wk_txt。
    wk = wk_txt
    if ("最有效" in wk or "单条最佳" in wk) and "赞0" in wk:
        bad("人面·零数据编结论", "周报用 0 赞的数据下了「最有效/最佳」的结论",
            "运营会说:'就一条,还 0 赞,你让我多产?' 宁可说'数据不够',也不能编")
        found += 1


    # (g) **假承诺:人面上说的能力,代码里没接线**(2026-07-14 人眼审抓到的,⑧ 的更深形态)
    #     卡片原话:"发完把链接发我认领" —— "发我认领"要 webhook 接住聊天消息 →
    #     `publish.fill_publish_link()` 是那个入口,而它**生产零调用、webhook 未接**:
    #     运营真把链接发给 bot,**石沉大海,没有任何东西在听**。功能没接线,话却已经说出去了。
    PROMISES = [
        ("发我认领", "fill_publish_link", "把链接发给 bot 认领 —— 要 webhook 接住聊天消息"),
        ("发给我", "fill_publish_link", "同上"),
        ("点按钮", "approve", "卡片按钮 —— 要 webhook 接住按钮点击"),
        ("点卡片", "approve", "同上"),
    ]
    for phrase, fn, need in PROMISES:
        if phrase not in blob:
            continue
        wired = _real_callers(fn) > 0     # **AST 数真调用点**;注释里提到名字不算(第一版就栽在这)
        if not wired:
            bad("人面·假承诺", f"卡片上说「{phrase}」,但 {fn}() **生产零调用**",
                f"{need}。**功能没接线,话却已经说出去了** —— 人照做,石沉大海。"
                f"要么接线,要么别说")
            found += 1

    if not found:
        ok("人面产物:没有给错读者/黑洞/空表头/半句话/零数据编结论/假承诺")
        print("      ⚠️ 但机器只能查这些**形式**问题。**'人打开顺不顺手'查不了**——")
        print("         每轮必须真渲染卡片/补拍单/周报,以人的眼睛读一遍,问'我会不会当场骂人'")


def audit_skill_shadowing() -> None:
    """⑨ 技能唯一真源:workspace 不许再藏技能(local-skills 是双源遮蔽的入口)。
    接线 `skills_lock.shadowed_skills()` —— 它此前只有测试在调 = 哨兵没站岗。"""
    print("\n── ⑨ 技能唯一真源(workspace 不许再藏技能)" + "─" * 20)
    from orchestrator.skills_lock import shadowed_skills
    local, inst = ROOT / "local-skills", ROOT / "skills"
    names = [x.name for x in local.iterdir() if x.is_dir()] if local.exists() else []

    def resolve(n):
        q = inst / n
        return str(q.resolve()) if q.exists() else None

    errs = shadowed_skills(names, resolve)
    if local.exists():
        bad("技能双源", "workspace 又出现 local-skills/",
            "技能唯一真源=qiaohe-skill 仓。local 优先于 skills/ → 技能仓的同名技能会被静默盖住,"
            "而 installed_drift 只比远程 HEAD,一个字都不报")
    for e in errs:
        bad("技能双源遮蔽", e)
    if not local.exists() and not errs:
        ok("技能唯一真源 = qiaohe-skill 仓(workspace 无 local-skills/,无遮蔽)")


# ══════════════════════════════════════════════════════════════════════════════
# ⑩ 幂等:所有"修复/同步"类写操作,跑两遍必须结果一样 —— 否则它不是修复,是破坏
#
#    2026-07-14 真跑 L14 抓到的:`restore()` **不幂等** —— 把备份里每条都无脑 create 一遍,
#    完全不看库里有没有。关键词库 32 条 → 真删 1 条(31)→ 跑一次 restore → **38 条**
#    (凭空多 7 条重复),而被误删的那条**始终没回来**。
#    **在还有数据的表上跑一次,整张表就翻倍污染 —— 它不是"恢复",是"复制粘贴"。**
#    而当时 test_restore.py 有 3 个测试、全绿 —— 它们**全在测最容易测的纯函数**(字段级 link 解析),
#    **真正会毁数据的那个行为(会不会重复插)一个字没测**。
#
#    规矩:凡是会写库的"修复/同步"操作,**必须有幂等回归锁**(tests/test_idempotent.py)。
# ══════════════════════════════════════════════════════════════════════════════
REPAIR_OPS = {
    "restore": "从备份恢复(只补缺的,不许重灌已有的)",
    "stamp_published_at": "补『实际发布日』(已有日期的绝不能再动,否则 cron 每天刷成今天、历史全乱)",
    "harvest_trends": "落灵感库(同一批热点投两遍,第二遍必须全被去重)",
    "mark_idea_converted": "灵感转化回填(重复调用=覆盖同一个值,不产生新记录)",
}


def audit_idempotency() -> None:
    print("\n── ⑩ 幂等(修复类写操作跑两遍必须一样,否则是破坏)" + "─" * 12)
    lock = ROOT / "tests" / "test_idempotent.py"
    if not lock.exists():
        bad("幂等", "tests/test_idempotent.py 不存在",
            "所有'修复/同步'类写操作必须有幂等回归锁 —— restore 不幂等曾把整张表翻倍污染")
        return
    src = lock.read_text(encoding="utf-8") + (ROOT / "tests" / "test_restore.py").read_text(encoding="utf-8")
    for fn, why in REPAIR_OPS.items():
        if fn not in src:
            bad("幂等·无锁", f"{fn}() 是写库的修复操作,却**没有幂等回归锁**",
                f"{why}。不幂等的'修复'= 破坏(restore 就跑一次翻倍污染过整张表)")
        else:
            ok(f"{fn}() 有幂等锁")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="只查代码,不触真库")
    a = ap.parse_args()
    from orchestrator import config
    print("═" * 70)
    print(f"  全体系对齐审查(硬门)  env={config.ENV_NAME}")
    print("  病:人想起来方便的逻辑,落实下来是 bug —— 造好了没接线 / 名不副实 / 数据支撑不了")
    print("═" * 70)

    audit_dead_code()
    audit_dead_config()
    audit_default_traps()
    audit_fake_fixtures()
    audit_skill_shadowing()
    audit_idempotency()
    if not a.offline:
        audit_views()
        audit_empty_gates()
        audit_human_surface()

    print("\n" + "═" * 70)
    if FAIL:
        print(f"  ❌ 对齐审查**未通过** —— {len(FAIL)} 处名实不符:")
        for f in FAIL:
            print(f"     · {f.split(' —— ')[0]}")
        print("\n  规矩:**要么真做出来,要么删掉**。别留着骗人。")
        print("═" * 70)
        return 1
    print("  ✅ 全体系对齐 —— 没有死码/死配置/空壳/名不副实/默认值陷阱/空门/假形态mock/人面缺陷/不幂等的修复")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
