#!/usr/bin/env python3
"""P6 压测(测试 Base):四场景。全部自清场(_STRESS 前缀,按 record_id 删)。
  S1 控量:同账号第 4 篇被拒(计入今日已发)
  S2 预算熔断:月成本超阈 → 拒绝生成、零新增成本
  S3 串行写压:15 连发 create/delete 全成功(429 退避兜底)
  S4 规模轮询:25 条混合状态一轮路由无崩溃、计数正确
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402
from orchestrator.engine import counts_toward_publish_quota, run  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name} {detail}")
    if not ok:
        FAILS.append(name)


def ct_rid(name: str) -> str:
    for r in feishu_io.list_records("内容类型表"):
        n = r["fields"].get("内容类型名")
        if isinstance(n, list):
            n = "".join(x.get("text", "") for x in n if isinstance(x, dict))
        if str(n) == name:
            return r["record_id"]
    raise KeyError(name)


def s1_quota() -> None:
    print("S1 控量:同账号(测试类型→玉子老师)第 4 篇拒绝")
    ct = ct_rid("测试类型")
    rids = []
    for i in range(3):
        rids.append(feishu_io.create_record("笔记表", {
            "排期编号": f"_STRESS-Q{i}", "状态": "已批准", "AI声明": True,
            "内容类型": [ct], "文案草稿": "压测稿"}))
        time.sleep(0.4)
    s = run(mode="heartbeat", llm_mode="stub", limit=100)
    quota_errors = [e for e in s["errors"] if "控量门" in e]
    # 该账号今天已有 _E2E-03 已发(1),故 3 条已批准里最多放行 2、至少拒 1
    now = datetime.now()
    total_today = sum(1 for r in feishu_io.list_records("笔记表")
                      if counts_toward_publish_quota(r["fields"], now)
                      and "玉子" in str(r["fields"].get("账号(自动)")))
    check("放行不超上限", total_today <= config.PER_ACCOUNT_DAILY_PUBLISH, f"(今日占额 {total_today})")
    check("超额被拒并告警", len(quota_errors) >= 1, f"(拒 {len(quota_errors)} 条)")
    for rid in rids:
        feishu_io.delete_record("笔记表", rid)
        time.sleep(0.3)


def s2_budget_fuse() -> None:
    print("S2 预算熔断:月成本超阈 → 拒生成零成本")
    import orchestrator.config as cfg
    old = cfg.BUDGET_MONTHLY_CNY
    cfg.BUDGET_MONTHLY_CNY = 0.01  # 本月已实花 ¥7+,必超
    rid = feishu_io.create_record("笔记表", {"排期编号": "_STRESS-B", "状态": "待出文案", "标题": "熔断测试"})
    time.sleep(0.5)
    try:
        s = run(mode="heartbeat", llm_mode="real", limit=100)  # real 触发熔断路径,但不应真调 LLM
        fused = [e for e in s["errors"] if "熔断" in e]
        check("熔断拒绝生成", len(fused) >= 1, f"({fused[:1]})")
        check("零新增成本", s["copy_cost_cny"] == 0.0)
        f = _get(rid)
        check("记录停在待出文案", f.get("状态") == "待出文案")
    finally:
        cfg.BUDGET_MONTHLY_CNY = old
        feishu_io.delete_record("笔记表", rid)


def s3_serial_write() -> None:
    print("S3 串行写压:15 连发 create+delete")
    ok = 0
    t0 = time.time()
    for i in range(15):
        try:
            rid = feishu_io.create_record("笔记表", {"排期编号": f"_STRESS-W{i}", "状态": "想法储备"})
            feishu_io.delete_record("笔记表", rid)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    第{i}次失败: {e}")
    check("30 次写操作全成功", ok == 15, f"({ok}/15, {time.time()-t0:.1f}s)")


def s4_scale() -> None:
    print("S4 规模轮询:25 条混合状态")
    states = ["想法储备", "待拍素材", "草稿待发", "暂缓归档", "已回流"]
    rids = []
    for i in range(25):
        rids.append(feishu_io.create_record("笔记表", {
            "排期编号": f"_STRESS-S{i:02d}", "状态": states[i % 5]}))
        time.sleep(0.3)
    t0 = time.time()
    s = run(mode="heartbeat", llm_mode="stub", limit=200)
    dur = time.time() - t0
    shoot = sum(1 for x in s["shoot"] if "_STRESS-S" in x)
    ideas = sum(1 for x in s["ideas"] if "_STRESS-S" in x)
    check("一轮完成无崩溃", True, f"({dur:.1f}s)")
    check("催拍计数=5", shoot == 5, f"(实际 {shoot})")
    check("储备计数=5", ideas == 5, f"(实际 {ideas})")
    for rid in rids:
        feishu_io.delete_record("笔记表", rid)
        time.sleep(0.25)


def _get(rid: str) -> dict:
    tid = config.tables()["笔记表"]
    return feishu_io._call(
        "GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records/{rid}")["record"]["fields"]


if __name__ == "__main__":
    assert config.ENV_NAME == "test", "只能测试 Base"
    for fn in (s1_quota, s2_budget_fuse, s3_serial_write, s4_scale):
        fn()
    print()
    if FAILS:
        print("❌ 压测失败:", FAILS)
        raise SystemExit(1)
    print("✅ 压测 4 场景全通过")
