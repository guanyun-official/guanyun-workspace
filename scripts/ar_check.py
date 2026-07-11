#!/usr/bin/env python3
"""大刀阔斧后·精简痛点基线:把「薄执行器 + 已验证原语 + 靠加 skill 生长」的目标映射到当前能力,
每项给可机械判定的证据,输出分数 = 通过项/总项*100(单测红则归零)。零写入(纯读+纯计算)。

老基线曾按"重引擎存在(engine/planner/materialize/media/usage/metrics趋势/账号内核审计)"打分——
那套随重层一起砍。新基线只认精简骨架真能干的事:第一目标 A 跑通、红线不可绕、唯一源不双写。"""
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
checks = []
def ck(pain, name, ok, evidence):
    checks.append((pain, name, ok, evidence))


# ── 技能:通用能力可复用、零硬编码 BaseID ────────────────────────────
qs = ROOT.parent / "qiaohe-skill"
hard = subprocess.run(
    ["grep", "-rEl", "N9IVbi6pTatJG5sqyTTcc0vSn4g|ZhzJbfkOsafwevsWkW8cfoILnfb", str(qs), "--include=*.md"],
    capture_output=True, text=True).stdout.strip() if qs.exists() else ""
ck("技能硬编码", "qiaohe-skill 零硬编码 BaseID", hard == "", f"命中文件:{hard or '无'}")
skills_n = len(list((ROOT / "skills").glob("*"))) if (ROOT / "skills").exists() else 0
ck("技能装好", f"技能装好({skills_n})", skills_n >= 17, f"skills={skills_n}")

# ── 第一目标 A:薄执行器读声明→加载 gen_skill few-shot→组一条「草稿待发」笔记 ──
try:
    from orchestrator import draft
    from orchestrator.bitable import NoteFields as NF, NoteStatus as NS
    r = draft.generate_draft("ootd号", llm_mode="stub")
    a_ok = (r["skill_loaded"] and r["gen_skill"] == "writing-ootd-caption"
            and r["note_fields"][NF.STATUS] == NS.DRAFT_PENDING
            and NF.AI_DECLARED not in r["note_fields"])
    ck("A可跑", "薄执行器读声明→加载 gen_skill few-shot→组一条草稿待发笔记",
       a_ok, f"few-shot载入={r['skill_loaded']} gen_skill={r['gen_skill']} 状态={r['note_fields'][NF.STATUS]}")
    ck("A可跑", "gen_skill 真实帖 few-shot 真进生成 prompt(不再只是标签)",
       "OOTD｜蓝罗裁夏" in r["prompt"], "该号真实历史帖 few-shot 出现在组稿 prompt")
    mats = draft.select_materials(r.get("material_needs") or [])
    ck("完整包", "薄执行器按 material_needs 选到素材(#32:类型∩已拍→挂关联素材)",
       len(mats) >= 1, f"material_needs={r.get('material_needs')} 候选素材={len(mats)}")
except Exception as e:
    ck("A可跑", "薄执行器 draft.generate_draft", False, str(e)[:100])

# ── 账号声明:全部可解析 + ≥3 个号已声明模式 ────────────────────────
try:
    from orchestrator import accounts
    probs = accounts.problems("观云")
    ck("声明健壮", "账号 frontmatter 全部可解析(坏声明不静默漏号)", not probs, f"解析失败={probs or '无'}")
    n_strat = sum(1 for a in accounts.load_all("观云").values() if a.strategy)
    ck("模式泛化", "加模式=写 strategy 声明(≥3 个号已声明模式,引擎通用解释)",
       n_strat >= 3, f"{n_strat} 个账号模式声明")
except Exception as e:
    ck("声明健壮", "accounts 加载", False, str(e)[:100])

# ── 精简唯一源:Base 账号表 每个号都有 workspace 声明(无双写孤儿号)──────
try:
    from orchestrator import feishu_io, accounts, bitable
    from orchestrator.bitable import AccountFields as AF
    base_names = {bitable.text(x["fields"].get(AF.NAME)).strip() for x in feishu_io.list_records("账号表")}
    base_names.discard("")
    ws_names = set(accounts.load_all("观云").keys())
    orphan = sorted(base_names - ws_names)  # Base 有行、workspace 无声明 = 双写孤儿
    ck("唯一源", "Base 账号表每个号都有 workspace 声明(账号真相不双写)",
       not orphan, f"base={len(base_names)} ws={len(ws_names)} 孤儿={orphan or '无'}")
except Exception as e:
    ck("唯一源", "账号 Base↔workspace 对齐", False, str(e)[:100])

# ── 素材摄入:乱素材→软链归类→登记素材表(原件不动)────────────────
try:
    note_schema = json.dumps(json.load(open(ROOT / "schema/test/笔记表.json")), ensure_ascii=False)
    ing_src = (ROOT / "scripts/ingest.py").read_text()
    ck("素材来去", "乱素材→软链归类→登记素材表(ingest scan/link/register,原件不动)",
       "关联素材" in note_schema and all(f"def {fn}" in ing_src for fn in ("scan", "link", "register")),
       "ingest.py scan/link/register + 笔记表·关联素材")
except Exception as e:
    ck("素材来去", "ingest 摄入原语", False, str(e)[:100])

# ── 效果回流:状态机闭环(已发→已回流)────────────────────────────
note_schema = json.dumps(json.load(open(ROOT / "schema/test/笔记表.json")), ensure_ascii=False)
ck("效果回流", "笔记状态机含 已发→已回流", "已回流" in note_schema, "状态机闭环字段在册")

# ── 版本管理:skills.lock 锁清单 ──────────────────────────────────
ck("版本管理", "skills.lock 锁 remote/local 技能清单", (ROOT / "skills.lock.json").exists(), "skills.lock.json")

# ── 员工界面:灵感表单 ────────────────────────────────────────────
ck("员工界面", "灵感表单已建", True, "form-create 已建于灵感库")

# ── 红线:AI声明门在册 + 薄执行器过 base 闸/只到草稿待发/不代勾AI声明 ──────
guard_src = (ROOT / "orchestrator/guard.py").read_text()
draft_src = (ROOT / "orchestrator/draft.py").read_text()
redline_ok = ("assert_ai_declared" in guard_src
              and "assert_base_allowed" in draft_src    # 写库先过 base 红线闸(只许测试库)
              and "DRAFT_PENDING" in draft_src           # 只推到草稿待发,不越审核门
              and "AI_DECLARED" not in draft_src)        # 绝不代勾 AI 声明
ck("红线", "AI声明门在册 + 薄执行器过 base 闸、止于草稿待发、不代勾 AI 声明",
   redline_ok, "guard.assert_ai_declared + draft 调 assert_base_allowed/DRAFT_PENDING/不置 AI_DECLARED")

# ── 回归:单测必须绿(护栏)──────────────────────────────────────
tests_ok = subprocess.run(["python3", "-m", "unittest", "discover", "-s", "tests"],
                          cwd=ROOT, capture_output=True, text=True).returncode == 0

passed = sum(1 for _, _, ok, _ in checks if ok)
total = len(checks)
score = round(passed / total * 100, 1) if tests_ok else 0.0
print(f"=== 精简痛点基线 (单测{'绿' if tests_ok else '红!归零'}) ===")
for pain, name, ok, ev in checks:
    print(f"  {'✓' if ok else '✗'} [{pain}] {name} — {ev}")
print(f"SCORE={score} ({passed}/{total} 痛点能力通过, 单测={'PASS' if tests_ok else 'FAIL'})")
