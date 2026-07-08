#!/usr/bin/env python3
"""P4 验收:模拟一天。测试 Base 播种 _SIM-P4-* 覆盖关键状态 → 跑引擎 → 断言流转 → 清场。
只动测试 Base(engine 的 Base 守卫兜底)。用法: ALERT_DRY_RUN=1 python3 scripts/sim_day.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402
from orchestrator.engine import run  # noqa: E402

MS = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731
NOW = datetime.now()

SEEDS = {
    "_SIM-P4-A": {"状态": "待出文案", "标题": "SIM文案生成"},
    "_SIM-P4-B": {"状态": "已批准", "标题": "SIM发布包", "文案草稿": "既有草稿", "AI声明": True},
    "_SIM-P4-C": {"状态": "待发布", "标题": "SIM发布检测", "AI声明": True,
                  "发布链接": {"link": "https://www.xiaohongshu.com/explore/sim", "text": "sim"}},
    "_SIM-P4-D": {"状态": "已发", "标题": "SIM回流收口", "实际发布日": MS(NOW - timedelta(days=8))},
    "_SIM-P4-E": {"状态": "待拍素材", "标题": "SIM催拍"},
    "_SIM-P4-F": {"状态": "想法储备", "标题": "SIM储备"},
}
EXPECT_STATE = {"_SIM-P4-A": "草稿待发", "_SIM-P4-B": "待发布", "_SIM-P4-C": "已发",
                "_SIM-P4-D": "已回流", "_SIM-P4-E": "待拍素材", "_SIM-P4-F": "想法储备"}


def main() -> int:
    assert config.ENV_NAME == "test", f"只能在测试 Base 跑,当前 env={config.ENV_NAME}"
    rids: dict[str, str] = {}
    print("① 播种", len(SEEDS), "条 _SIM 笔记")
    for name, fields in SEEDS.items():
        rids[name] = feishu_io.create_record("笔记表", {"排期编号": name, **fields})

    print("② 跑引擎 heartbeat(llm=stub)")
    s = run(mode="heartbeat", llm_mode="stub", limit=100)

    print("③ 断言流转")
    fails = []
    for name, rid in rids.items():
        tid = config.tables()["笔记表"]
        d = feishu_io._call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{rid}")
        f = d["record"]["fields"]
        got = f.get("状态")
        ok = got == EXPECT_STATE[name]
        extra = ""
        if name == "_SIM-P4-A":
            ok = ok and bool(f.get("文案草稿")) and f.get("AI声明") is True
            extra = f" 草稿={'有' if f.get('文案草稿') else '无'} AI声明={f.get('AI声明')}"
        if name == "_SIM-P4-C":
            ok = ok and bool(f.get("实际发布日"))
            extra = f" 实际发布日={'已回填' if f.get('实际发布日') else '缺'}"
        print(f"  {'✓' if ok else '✗'} {name}: {SEEDS[name]['状态']} → {got}{extra}")
        if not ok:
            fails.append(name)
    assert "SIM催拍" in "".join(s.get("shoot", [])) or any("_SIM-P4-E" in x for x in s.get("shoot", [])), "催拍未列入巡检"
    assert any("_SIM-P4-F" in x for x in s.get("ideas", [])), "储备未列入日报清单"
    print("  ✓ 催拍/储备 进入摘要")

    print("④ 清场(_SIM 全删,只删本脚本建的 record_id)")
    tid = config.tables()["笔记表"]
    for rid in rids.values():
        feishu_io._call("DELETE", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{rid}")

    if fails:
        print("❌ 模拟一天失败:", fails)
        return 1
    print("✅ 模拟一天通过:6 状态全部按 runbook 流转,运行日志已写")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
