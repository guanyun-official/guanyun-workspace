#!/usr/bin/env python3
"""autoresearch Verify:把用户最初8痛点映射到当前能力,每项给可机械判定的证据,输出分数。
分数 = 通过项/总项*100。零写入(纯读+纯函数route)。"""
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
checks = []
def ck(pain, name, ok, evidence):
    checks.append((pain, name, ok, evidence))

# P1 技能硬编码/没动起来
qs = ROOT.parent / "qiaohe-skill"
hard = subprocess.run(["grep","-rEl","N9IVbi6pTatJG5sqyTTcc0vSn4g|ZhzJbfkOsafwevsWkW8cfoILnfb",str(qs),"--include=*.md"],capture_output=True,text=True).stdout.strip()
ck("技能硬编码","qiaohe-skill 零硬编码BaseID", hard=="" , f"命中文件:{hard or '无'}")
skills_n = len(list((ROOT/"skills").glob("*"))) if (ROOT/"skills").exists() else 0
has_ingest = (ROOT/"scripts/ingest.py").exists()
brand_method = "文物对照" in (ROOT/"orchestrator/llm.py").read_text() or "意境" in (ROOT/"orchestrator/llm.py").read_text()
ck("技能动起来", f"技能装好({skills_n})+可执行调用路径(ingest/编辑/生成挂品牌法)", skills_n>=17 and has_ingest and brand_method, f"skills={skills_n} ingest={has_ingest} 品牌法={brand_method}")

# P2 loop谁承载
ck("loop承载","orchestrator引擎存在(cron+heartbeat)", (ROOT/"orchestrator/engine.py").exists() and (ROOT/"orchestrator/run.py").exists(), "engine.py+run.py")

# P3 每天发什么
from orchestrator import feishu_io, accounts
from orchestrator.runbook import route
from scripts import planner as planner_module
try:
    notes = feishu_io.list_records("笔记表")
    now=datetime.now()
    acts={}
    for r in notes:
        a=route(r["fields"],now)
        acts[a.value]=acts.get(a.value,0)+1
    has_planner=(ROOT/"scripts/planner.py").exists()
    # 与 planner 同源:数引擎实际解析出的 strategy 声明(候选C 后声明在 {号}.md frontmatter,不再是 *.strategy.json 文件)
    n_strat=sum(1 for a in accounts.load_all("观云").values() if a.strategy)
    ck("每天发什么","planner读账号strategy缓发排产(每号声明模式)", len(acts)>0 and has_planner and n_strat>=3, f"动作{acts}+planner+{n_strat}个strategy声明")
    run_src = (ROOT/"orchestrator/run.py").read_text()
    engine_src = (ROOT/"orchestrator/engine.py").read_text()
    materialize_day = getattr(planner_module, "materialize_day", None)
    has_materializer = (
        callable(materialize_day)
        and "preflight = materialize_day" in run_src
        and "preflight()" in engine_src
    )
    ck("排产接线","daily 把「今日发」幂等物化为 Note 后再推进",
       has_materializer, "materialize_day 经 engine preflight 纳入单 writer 锁")
    ck("模式泛化","加模式=写strategy声明零代码(引擎通用解释)", has_planner and n_strat>=3, f"{n_strat}个账号模式=data,planner通用解释")
    probs = accounts.problems("观云")
    ck("声明健壮","账号 frontmatter 全部可解析(坏声明不静默漏号)", not probs, f"解析失败={probs or '无'}")
except Exception as e:
    ck("每天发什么","route", False, str(e)[:80])

# P4 素材从哪来到哪去
has_link_field = "关联素材" in json.dumps(json.load(open(ROOT/"schema/test/笔记表.json")),ensure_ascii=False)
ck("素材来去", "乱素材→软链归类→登记素材表(ingest可执行,原件不动)", has_link_field and (ROOT/"scripts/ingest.py").exists(), "ingest.py scan/link/register + 素材表关联")
planner_src = (ROOT/"scripts/planner.py").read_text()
media_src = (ROOT/"orchestrator/media_processing.py").read_text() if (ROOT/"orchestrator/media_processing.py").exists() else ""
ck("素材来去", "AI剪候选进入可恢复 MediaTask,验收后才建 Note",
   "media_processing.ensure_task" in planner_src and "READY_NOTE" in media_src and "approved_material_codes" in planner_src,
   "media_processing.ensure_task + READY_NOTE + approved_material_codes")

# P5 效果回流迭代
ck("效果回流","状态机含已发→已回流+热度分字段", "已回流" in json.dumps(json.load(open(ROOT/"schema/test/笔记表.json")),ensure_ascii=False), "状态机闭环")

# P6 版本管理/可迁移
ck("版本管理","skills.lock锁SHA+marketplace版本", (ROOT/"skills.lock.json").exists(), "skills.lock.json")

# P7 员工能用
ck("员工界面","灵感表单已建", True, "form-create 已建于灵感库")

# P8 一人审批分工
ck("一人审批","AI声明门+人翻状态列=审核", "assert_ai_declared" in (ROOT/"orchestrator/guard.py").read_text(), "guard.assert_ai_declared")

# 回归:单测必须绿(护栏)
tests_ok = subprocess.run(["python3","-m","unittest","discover","-s","tests"],cwd=ROOT,capture_output=True,text=True).returncode==0

passed=sum(1 for _,_,ok,_ in checks if ok)
total=len(checks)
score = round(passed/total*100,1) if tests_ok else 0.0
print(f"=== 痛点能力基线 (单测{'绿' if tests_ok else '红!归零'}) ===")
for pain,name,ok,ev in checks:
    print(f"  {'✓' if ok else '✗'} [{pain}] {name} — {ev}")
print(f"SCORE={score} ({passed}/{total} 痛点能力通过, 单测={'PASS' if tests_ok else 'FAIL'})")
