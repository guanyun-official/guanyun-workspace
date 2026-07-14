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
  ⑪ 悬空引用   —— 文档/代码提到已删的模块名/脚本名/开关名,当成还活着的东西在用
                  (2026-07-14 大手术删了 orchestrator/{dispatch,draft,…} 一整批,
                   谁还在提它们,谁就在骗人)

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
    # ── 2026-07-14 拆导轨(含本轮清理开发期门)留下的孤儿原语 ─────────────────────────
    #   它们的**唯一调用者**是被删掉的导轨脚本/cron/开发期假检查,函数本身没坏,只是没人调了。
    #   "做出来"(接新调用者)还是"删掉",都是 orchestrator/ 的判断,不是清理开发期门这次改动该做的决定——
    #   如实记账,留给下一轮判断。**不是静默豁免**:每条都写死它的孤儿身世,查得到。
    "accounts.problems":
        "唯一调用者曾是 scripts/ar_check.py(本轮 2026-07-14 删除——'测措辞'的假检查,grep 源码算分)。"
        "账号 frontmatter 健壮性校验本身没坏,该不该给它接新调用者,留给你判断。",
    "skills_lock.validate":
        "唯一调用者曾是 scripts/check_p1.sh(本轮删除,同类假检查)。",
    "skills_lock.installed_drift":
        "唯一调用者曾是 scripts/ar_check.py(本轮删除)。",
    "lock.write_lock":
        "唯一调用者是 run_day/dispatch 的写循环——均已删(见 docs/架构.md『已经删掉的(2026-07-14)』)。"
        "并发锁原语还在,等新写路径需要时再接。",
    "trends.fill_missing_bodies":
        "唯一调用者是 daily_dispatch --write(cron,已删——『心跳也是导轨』,docs/架构.md 4.1)。",
    "cost.budget_alert":
        "唯一调用者是 daily_dispatch(cron,已删,同上)。",
    "cockpit.weekly_schedule_card":
        "大手术后的 orchestrator/cli.py(薄 Action Interface)还没给它接一个动词——"
        "`report` 动词现在吐的是 report.weekly_text,不是这张卡片。接不接、接哪个动词,不是本轮门清理的范围。",
    "feishu_io.delete_record":
        "通用删除原语,目前没有任何脚本/CLI 动词调用它(手工/REPL 场景用;"
        "restore_tables.py 文档里『真删一条再恢复』的验证就是手动调它做的)。",
    "ingest.segment_note":
        "ADR-0004 §4 的视频分段备注原语;视频处理链路(ADR-0007)还没写调用它的那段代码。",
    "ark.chat":
        "通用 LLM 纯文本 chat 原语;llm.py(替 agent 调另一个模型写稿的导轨)已删,现在没人调它。",
    "materials.by_ids":
        "按 id 批量取素材事实的原语;cli.py 的 material.list 走的是 materials.facts(),没有走它。",
    "netpan.logged_in":
        "ADR-0004 提到的登录态前置检查原语,还没有 cron/脚本接它(目前人工确认登录态)。",
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

      4. 第四次(2026-07-14):它只数 `ast.Call`(被按名字调用),**不数"被当成值引用"**。
         可这个仓的钩子架构(ADR-0006「关节焊死、叶子智能」)**整个靠传函数值实现**:
             default_hooks() → return compose.ai_decide, compose.execute      # 依赖注入
             _EXECUTORS = {"拼图": compose_execute, "AI封面": cover_execute}   # 注册表
         这些函数**永远不会被按名字调用**,却全都真接在线上 —— 老实现一律判死码,**假红**。
         而假红比漏报更毒:喊三次狼来了,这道门就再没人看了。
         现在:被 Call 调、或被当**值**引用(赋给变量/进 dict/进 return/当实参),都算接线。

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
            elif isinstance(node, (ast.Name, ast.Attribute)):
                # 被当**值**引用 = 依赖注入/注册表接线(钩子从不按名字调用)
                name = getattr(node, "id", None) or getattr(node, "attr", None)
                if name == fn:
                    n += 1
    # **门是 shell 脚本**(check_p1-6.sh 里内嵌 python heredoc 调 orchestrator)。
    # 只扫 .py 会看不见它们 —— 我第一版就把 `skills_lock.validate()` 判成死码,
    # 而它明明在 check_p1.sh 里被调用着。**又是假红**,而假红比漏报更毒。
    # shell 里没法 AST,只能文本匹配;这里可接受:.sh 里几乎没有大段注释来骗它。
    for sh in sorted((ROOT / "scripts").glob("*.sh")):
        n += len(re.findall(rf"\b{re.escape(fn)}\s*\(", sh.read_text(encoding="utf-8", errors="ignore")))
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
            # 2026-07-14:这里原来用 **regex** 数 `fn(` —— 而 `_real_callers` 的 docstring 里
            # **白纸黑字骂过这个写法**(注释里出现名字也算数、把检查骗成摆设),说"已改用 AST"。
            # **可死码检查从来没换过去。** 审查器里躺着两套数调用点的逻辑,一新一旧,
            # 而旧的那套正是它自己骂过的那套。—— 检查器自己得了它要抓的病。
            #
            # 而且 regex 只认 `fn(`(被调用),**认不出被当值引用的钩子**:
            #     default_hooks() → return compose.ai_decide, compose.execute   # 没有括号!
            # 于是整个 ADR-0006 的钩子架构(关节焊死、叶子智能)被一律判成死码 —— **假红**。
            # 统一到 AST:被调用 or 被当值引用,都算接线。
            if _real_callers(fn) == 0:
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
#   自称"验收/检查/探针"却没人跑的脚本 —— **验收器自己没被验收过**
#
#   2026-07-14 真事(那个脚本本身后来已删,教训留着):某个自称"综合验收"的脚本,
#     · review_gate 不跑它、cron 不跑它、任何脚本都不跑它 —— **零调用**
#     · 手动一跑当场崩掉,它的提示却还在传播一句已被真跑证伪的话
#   "验收器不在门里 = 那条件从来没被机器验过",我却一直以为它验过了。
#   这就是"人想起来方便的逻辑"最贵的一种:连查错的东西本身都没人查。
#
#   规则**故意写窄**(误报比漏报更糟——狼来了三次,门就废了):
#   只管"自称验收/检查"的脚本。`python3 -m orchestrator <动词>` 这类**给人和 agent 手调的
#   Action Interface**(board / material.* / note.* / idea.* / compose / schedule.* …)
#   本来就没有上游调用者,不算死。
_VERIFIER_HINTS = ("probe", "verify", "check_", "audit", "smoke")
_GATE_RUNNERS = ("scripts/review_gate.sh", "Makefile", ".github")


def audit_dead_verifiers() -> None:
    print("\n── ①b 没人跑的验收器(验收器自己没被验收过)" + "─" * 20)
    runners = ""
    for rel in _GATE_RUNNERS:
        p = ROOT / rel
        if p.is_file():
            runners += p.read_text(encoding="utf-8", errors="ignore")
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    runners += f.read_text(encoding="utf-8", errors="ignore")
    # 其它脚本互相调用也算"被跑"(如 check_p3.sh 里 python3 xxx.py)
    for f in (ROOT / "scripts").glob("*.sh"):
        runners += f.read_text(encoding="utf-8", errors="ignore")

    found = 0
    for f in sorted((ROOT / "scripts").glob("*.py")):
        if not any(h in f.name for h in _VERIFIER_HINTS):
            continue
        if f.name in runners or f.stem in runners:
            ok(f"{f.name} 被门真调用")
            continue
        bad("死验收器", f"`scripts/{f.name}` 自称验收/检查,却**没有任何门跑它**",
            "没人跑的验收器 = 零价值,而且会烂在暗处(崩了都没人知道),"
            "更坏的是**让人误以为那件事已经被验过了**。要么接进 review_gate,要么删掉")
        found += 1
    if not found:
        print("      (自称验收的脚本都真接在门上——没有'验收器自己没被验收'的)")


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
#   `harvest_trends`/`write` **不在这张单子里**:cli.py 的 `idea.add` 动词按位置传参
#   (`trends.harvest_trends(items, brand, a.write)`),这条检查只认 `write=` 关键字写法,
#   会把"位置传参"误判成"没传"——**假红**(2026-07-14 真跑验出来的),故意不盯这一对。
WATCH_DEFAULTS = [("log_run", "table"), ("collect", "mode")]


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
    # 门真正的比对源 = **LLM 眼睛看得见的一切**:灵感标题(title_seed)+ 灵感正文(source_text,
    # 当情报进 prompt 学结构)+ 技能 few-shot 真实帖。标题是最起码的那个 —— 没标题连活都派不出去。
    ("防搬运门 assert_no_source_leak", "灵感库", "标题",
     "灵感标题**就是 title_seed**,直接进 prompt。全空 → 派不出活,爆款模仿链路断在源头"),
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

    # 2026-07-14 大手术:曾经这里还有 audit_gate_covers_prompt() —— 读 orchestrator/draft.py 源码,
    # 查"进了 compose_prompt 的外来文本是否都进了 assert_no_source_leak"。draft.py 整个已删:
    # harness 不再替 agent 组 prompt(那是导轨),agent 自己读技能、自己写稿。
    # 这条检查查的是**已经不存在的调用图**,查不出东西了,删掉——不是留着骗人地"一直绿"。
    # 防搬运门本身(guard.assert_no_source_leak,notes.write_draft 出口调用)还在,没有变弱。


# ══════════════════════════════════════════════════════════════════════════════
# 2026-07-14 大手术:这里曾经是 ⑧ 人面产物审查(audit_human_surface,连带 AGENT_ONLY /
# _scan_agent_only)。它调 `shotlist.shot_needs("巧荷")` 拿补拍单数据——那个函数已删:
# 谁该补拍是 agent 的判断,harness 不再算。这条检查查的是**已经不存在的调用图**,直接崩。
# 更深一层:CLAUDE.md 自己的规矩是「审查员必须是 agent,不能是脚本」——「人会不会懵」
# 「话有没有骗人」这类人面质量判断,本来就不该靠 regex 机械查,是 loop 真渲染 + 人/子 agent
# 读一遍的事(见 docs/架构.md 第六节)。删掉,不是留着骗人地"一直绿"。
# ══════════════════════════════════════════════════════════════════════════════


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
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# ⑪ 悬空引用:提到已删的模块名/脚本名/开关名 —— **文档在骗人**(说着一个已经不存在的东西)
#
#    2026-07-14 大手术删了 orchestrator/{dispatch,draft,llm,vision,processing} +
#    scripts/{tag_materials,daily_dispatch,draft_one,today,ingest,full_stack_probe,…} +
#    GY_DRAFT_*/GY_VISION_*/GY_TAG_CONCURRENCY/GY_PROCESSING_ENABLED/GY_INGEST_VIDEO。
#    这份清单本身**只在这里以数据形式存在**——本文件被排除在扫描范围外(否则查自己会自己报红)。
#
#    docs/架构.md、CLAUDE.md、docs/adr/ 允许提:架构.md 有专门的"已经删掉的"小节;
#    ADR 是历史决策记录(docs/架构.md 自己的规矩:"已定的事,别重新翻案;要翻先改 ADR")——
#    拿这道检查去逼着改写历史决策记录,本身就是错的。
#    别的地方提到,只要**同一行**标一句"已删/删掉/曾经/老实现"这类历史措辞就放行;
#    没标 = 当前用法在骗人,报红。
# ══════════════════════════════════════════════════════════════════════════════
STALE_REFS = [
    (r"orchestrator\.draft\b|from orchestrator import[^\n]*\bdraft\b", "orchestrator.draft(导轨模块,已删)"),
    (r"orchestrator\.dispatch\b|from orchestrator import[^\n]*\bdispatch\b", "orchestrator.dispatch(导轨模块,已删)"),
    (r"scripts[./]tag_materials", "scripts/tag_materials.py(已删)"),
    (r"scripts[./]draft_one", "scripts/draft_one.py(已删)"),
    (r"scripts[./]daily_dispatch", "scripts/daily_dispatch.py(已删)"),
    (r"scripts[./]today\b", "scripts/today.py(已删)"),
    (r"scripts[./]ingest\b", "scripts/ingest.py(已删;别跟 orchestrator.ingest 搞混,那个还活着)"),
    (r"full_stack_probe", "full_stack_probe(已删,17条链路真跑并入了 review_gate --full 的④)"),
    (r"\bGY_DRAFT_\w*", "GY_DRAFT_*(已删,harness 不再替 agent 调另一个模型写稿)"),
    (r"\bGY_VISION_\w*", "GY_VISION_*(已删,harness 不再替 agent 调另一个模型看图)"),
    (r"\bGY_TAG_CONCURRENCY\b", "GY_TAG_CONCURRENCY(已删)"),
    (r"\bGY_PROCESSING_ENABLED\b", "GY_PROCESSING_ENABLED(已删,要不要加工没有开关,是判断)"),
    (r"\bGY_INGEST_VIDEO\b", "GY_INGEST_VIDEO(已删)"),
]
_HISTORY_MARK = re.compile(r"删|曾经|老实现|已卸|已下线|原本")   # "删"是最广的一个:已删/删掉/被删/【删】全接住
_STALE_EXEMPT_FILES = {"CLAUDE.md", "docs/架构.md"}     # 明确允许历史提及(架构.md 有专门小节)
_STALE_EXEMPT_DIRS = {"docs/adr"}                        # ADR = 历史决策记录,别逼着改写历史
_STALE_SKIP_DIRS = {".git", "__pycache__", "skills", ".pytest_cache", ".omx"}  # skills=外部技能仓的符号链接,不是本仓


def audit_stale_references() -> None:
    print("\n── ⑪ 悬空引用(提到已删的模块/脚本/开关 —— 文档在骗人)" + "─" * 12)
    found = 0
    self_file = Path(__file__).resolve()
    for ext in ("*.py", "*.md", "*.sh"):
        for p in ROOT.rglob(ext):
            if p.resolve() == self_file or any(part in _STALE_SKIP_DIRS for part in p.parts):
                continue
            rel = str(p.relative_to(ROOT))
            if rel in _STALE_EXEMPT_FILES or any(rel.startswith(d + "/") for d in _STALE_EXEMPT_DIRS):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _HISTORY_MARK.search(line):
                    continue                       # 标了历史措辞 = 在讲过去,放行
                for pat, why in STALE_REFS:
                    if re.search(pat, line):
                        bad("悬空引用", f"{rel}:{i}  {why}", f"这行:{line.strip()[:80]}")
                        found += 1
    if not found:
        ok("全仓没有悬空引用已删的模块/脚本/开关(或都标了'已删/曾经'等历史措辞)")



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
    audit_dead_verifiers()
    audit_dead_config()
    audit_default_traps()
    audit_fake_fixtures()
    audit_skill_shadowing()
    audit_stale_references()
    if not a.offline:
        audit_views()
        audit_empty_gates()

    print("\n" + "═" * 70)
    if FAIL:
        print(f"  ❌ 对齐审查**未通过** —— {len(FAIL)} 处名实不符:")
        for f in FAIL:
            print(f"     · {f.split(' —— ')[0]}")
        print("\n  规矩:**要么真做出来,要么删掉**。别留着骗人。")
        print("═" * 70)
        return 1
    print("  ✅ 全体系对齐 —— 没有死码/死配置/空壳/名不副实/默认值陷阱/空门/假形态mock/悬空引用")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
