"""回流采集薄执行器 CLI（每周一轮:采集互动数据 + 按 playbook 复盘)。

  python3 -m scripts.collect_metrics            # stub(零成本,不写;验结构)
  python3 -m scripts.collect_metrics --real     # xhs-extract-master 非登录真采集→写回测试库 + 复盘

采集能力是可替换 skill(xhs-extract-master 非登录,零封号不用我方账号);薄执行器只编排。
红线:只读采集 + 只写测试库;绝不碰发布。
**什么时候采,是 agent 的判断** —— 它自己去 crontab 里设(harness 给它 shell 这只手)。
"""
from __future__ import annotations

import argparse
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/collect_metrics.py 也能跑(不止 -m)

from orchestrator import collect, config, feishu_io, metrics
from orchestrator.bitable import NoteFields as NF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    # **有真链接就真采。** GY_METRICS_MODE 已删(2026-07-14):
    # 它存在的唯一理由是"让离线单测不触网",而**单测已全删**(只剩红线),这个理由没了。
    # 真采是零凭证、几乎免费的(xhs-extract-master 非登录);没链接的自然采不到,不需要开关。
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} 真采(有链接的已发帖)")
    s = collect.collect_and_writeback(mode="real", limit=a.limit)
    feishu_io.log_run(summary=f"回流 采集{s['采集']}写回{s['写回']}", action="回流", table="笔记表")   # 记运行日志(复盘据此)
    if s["采集"] > 0 and s["写回"] == 0:   # 有已发却全采不到=疑取数挂→告警
        from orchestrator import alerts
        alerts.send(f"回流全失败:{s['采集']} 条已发采集写回 0,疑登录态过期或取数挂", title="巧荷回流⚠️")
    print("采集写回:", json.dumps(s, ensure_ascii=False))
    # 复盘:按 playbook 聚合已发 note 效果(哪套方法论有效),喂周复盘/调权重
    fields = [r["fields"] for r in feishu_io.list_records(NF.TABLE)]
    print("按方法论复盘:", json.dumps(metrics.aggregate_by_playbook(fields), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
