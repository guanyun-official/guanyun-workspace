#!/usr/bin/env python3
"""UAT 精简版:补齐未覆盖三路径(打回/催审超时/暂缓复活)+清 _UAT 残留。stub 零成本。"""
import sys, time
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import config, feishu_io
from orchestrator.engine import run

MS = lambda d: int(d.timestamp()*1000)
assert config.ENV_NAME == "test"
res = {}

def notes(prefix):
    out={}
    for r in feishu_io.list_records("笔记表"):
        t=r["fields"].get("排期编号")
        if isinstance(t,list): t="".join(x.get("text","") for x in t if isinstance(x,dict))
        if str(t).startswith(prefix): out[str(t)]=r
    return out

def st(rid):
    tid=config.tables()["笔记表"]
    return feishu_io._call("GET",f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{rid}")["record"]["fields"]

# 清阵亡剧团残留(笔记表 _UAT-A*)
n=0
for t,r in notes("_UAT-").items():
    feishu_io.delete_record("笔记表", r["record_id"]); n+=1; time.sleep(0.3)
print(f"清理既有 _UAT 残留 {n} 条")

r1=feishu_io.create_record("笔记表",{"排期编号":"_UAT-MIN1","状态":"待出文案","标题":"打回路径"})
r2=feishu_io.create_record("笔记表",{"排期编号":"_UAT-MIN2","状态":"草稿待发","标题":"催审超时","计划发布日":MS(datetime.now()-timedelta(days=3))})
r3=feishu_io.create_record("笔记表",{"排期编号":"_UAT-MIN3","状态":"待出文案","标题":"暂缓复活"})
time.sleep(1)
s=run(mode="heartbeat",llm_mode="stub",limit=200)
f1=st(r1)
res["生成(前置)"] = f1.get("状态")=="草稿待发" and f1.get("AI声明") is True
res["催审超时"] = any("_UAT-MIN2" in x for x in s["review"])
# 打回→再生成→通过
feishu_io.update_record("笔记表",r1,{"状态":"待出文案"}); time.sleep(0.5)
run(mode="heartbeat",llm_mode="stub",limit=200)
res["打回后再生成"] = st(r1).get("状态")=="草稿待发"
feishu_io.update_record("笔记表",r1,{"状态":"已批准"}); time.sleep(0.5)
run(mode="heartbeat",llm_mode="stub",limit=200)
res["通过→待发布"] = st(r1).get("状态")=="待发布"
# 暂缓复活
feishu_io.update_record("笔记表",r3,{"状态":"暂缓归档"}); time.sleep(0.5)
run(mode="heartbeat",llm_mode="stub",limit=200)
res["暂缓无动作"] = st(r3).get("状态")=="暂缓归档"
feishu_io.update_record("笔记表",r3,{"状态":"待出文案"}); time.sleep(0.5)
run(mode="heartbeat",llm_mode="stub",limit=200)
res["复活再生成"] = st(r3).get("状态")=="草稿待发"
# 清场
for rid in (r1,r2,r3): feishu_io.delete_record("笔记表",rid); time.sleep(0.3)
left=len(notes("_UAT-"))
print(f"清场后残留:{left}")
for k,v in res.items(): print(("  ✓ " if v else "  ✗ ")+k)
sys.exit(0 if all(res.values()) and left==0 else 1)
