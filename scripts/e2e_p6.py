#!/usr/bin/env python3
"""P6 端到端演练(测试 Base):3 条真笔记(3 账号×3 内容类型)走 待出文案→草稿待发→已批准→待发布→已发。
分阶段跑,人审(操盘手读稿定夺)在 gen 与 approve 之间:
  python3 scripts/e2e_p6.py seed          # 播种 3 条 _E2E(待出文案,挂真实内容类型关联)
  python3 scripts/e2e_p6.py gen [--real]  # 引擎生成文案(默认 stub;--real 走 claude -p)并打印稿件供人审
  python3 scripts/e2e_p6.py approve --pass 01,02 --reject 03   # 人审结果落表(打回→待出文案)
  python3 scripts/e2e_p6.py publish       # 引擎组装发布包;再模拟人回填发布链接;引擎置已发
  python3 scripts/e2e_p6.py report        # 汇总:各条状态+打回率
记录保留在测试 Base 作演练证据(前缀 _E2E-)。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402
from orchestrator.engine import run  # noqa: E402

SEEDS = {
    "_E2E-01": {"标题": "宁靖王夫人吴氏墓立领短袖衫,全网孤品1:1复原", "ctype": "文物对照",
                "脚本·分镜": "考据点:江西南昌明代宁靖王夫人吴氏墓出土;不魔改立领、有据可依;暗花绞罗面料"},
    "_E2E-02": {"标题": "孔府月影蓝暗花绞罗对襟衫·夏日通勤OOTD", "ctype": "唯美ootd",
                "脚本·分镜": "素材:素材库/巧荷对比/03-成片/DB001_唯美卡点15s.base.mp4(15s卡点成片);调性清冷唯美克制"},
    "_E2E-03": {"标题": "绞罗面料夏天怎么养?三件事说清", "ctype": "测试类型",
                "脚本·分镜": "面料通识科普:非遗绞罗,透气孔隙结构;洗护/存放/防勾丝"},
}


def _ct_map() -> dict[str, str]:
    ct = {}
    for r in feishu_io.list_records("内容类型表"):
        name = r["fields"].get("内容类型名")
        if isinstance(name, list):
            name = "".join(x.get("text", "") for x in name if isinstance(x, dict))
        ct[str(name)] = r["record_id"]
    return ct


def _e2e_records() -> dict[str, dict]:
    out = {}
    for r in feishu_io.list_records("笔记表"):
        f = r["fields"]
        t = f.get("排期编号")
        if isinstance(t, list):
            t = "".join(x.get("text", "") for x in t if isinstance(x, dict))
        if str(t).startswith("_E2E-"):
            out[str(t)] = {"rid": r["record_id"], "fields": f}
    return out


def cmd_seed() -> None:
    assert config.ENV_NAME == "test", "只能测试 Base"
    ct = _ct_map()
    for name, s in SEEDS.items():
        feishu_io.create_record("笔记表", {
            "排期编号": name, "标题": s["标题"], "状态": "待出文案",
            "内容类型": [ct[s["ctype"]]], "脚本·分镜": s["脚本·分镜"],
        })
        print(f"  播种 {name} [{s['ctype']}]")
        time.sleep(0.5)


def cmd_gen(real: bool) -> None:
    s = run(mode="heartbeat", llm_mode="real" if real else "stub", limit=100)
    print(f"\n本轮生成成本 ¥{s['copy_cost_cny']:.2f}")
    print("\n===== 稿件(供人审) =====")
    for name, rec in sorted(_e2e_records().items()):
        f = rec["fields"]
        print(f"\n--- {name} | 状态:{f.get('状态')} | 账号:{_txt(f.get('账号'))}")
        print(_txt(f.get("文案草稿"))[:500])


def cmd_approve(passed: list[str], rejected: list[str]) -> None:
    recs = _e2e_records()
    for suffix in passed:
        name = f"_E2E-{suffix}"
        feishu_io.update_record("笔记表", recs[name]["rid"], {"状态": "已批准"})
        print(f"  ✓ 通过 {name}")
        time.sleep(0.5)
    for suffix in rejected:
        name = f"_E2E-{suffix}"
        feishu_io.update_record("笔记表", recs[name]["rid"], {"状态": "待出文案"})
        print(f"  ↩ 打回 {name}(回待出文案)")
        time.sleep(0.5)


def cmd_publish() -> None:
    run(mode="heartbeat", llm_mode="stub", limit=100)  # 已批准→待发布(发布包卡片真发)
    time.sleep(1)
    for name, rec in sorted(_e2e_records().items()):
        f = rec["fields"] = _refresh(rec["rid"])
        if f.get("状态") == "待发布":
            feishu_io.update_record("笔记表", rec["rid"], {
                "发布链接": {"link": f"https://www.xiaohongshu.com/explore/e2e-{name[-2:]}", "text": "演练回填"}})
            print(f"  模拟人发布并回填链接: {name}")
            time.sleep(0.5)
    run(mode="heartbeat", llm_mode="stub", limit=100)  # 待发布+链接→已发


def cmd_report() -> None:
    recs = _e2e_records()
    total = len(SEEDS)
    rejected = 0
    for name, rec in sorted(recs.items()):
        f = _refresh(rec["rid"])
        print(f"  {name}: 状态={f.get('状态')} AI声明={f.get('AI声明')} "
              f"实际发布日={'有' if f.get('实际发布日') else '无'}")
    log = [r for r in feishu_io.list_records("运行日志表") if "打回" in str(r['fields'].get('摘要', ''))]
    print(f"\n  演练规模:{total} 条;运行日志相关条目:{len(log)}")


def _refresh(rid: str) -> dict:
    tid = config.tables()["笔记表"]
    d = feishu_io._call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{rid}")
    return d["record"]["fields"]


def _txt(v) -> str:
    if isinstance(v, list):
        return ",".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
    return str(v or "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["seed", "gen", "approve", "publish", "report"])
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--pass", dest="passed", default="")
    ap.add_argument("--reject", dest="rejected", default="")
    a = ap.parse_args()
    if a.phase == "seed":
        cmd_seed()
    elif a.phase == "gen":
        cmd_gen(a.real)
    elif a.phase == "approve":
        cmd_approve([x for x in a.passed.split(",") if x], [x for x in a.rejected.split(",") if x])
    elif a.phase == "publish":
        cmd_publish()
    else:
        cmd_report()
