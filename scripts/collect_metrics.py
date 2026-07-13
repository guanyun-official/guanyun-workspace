"""回流采集薄执行器 CLI（每周一轮:采集互动数据 + 按 playbook 复盘)。

  python3 -m scripts.collect_metrics            # stub(零成本,不写;验结构)
  python3 -m scripts.collect_metrics --real     # xhs-extract-master 非登录真采集→写回测试库 + 复盘

采集能力是可替换 skill(xhs-extract-master 非登录,零封号不用我方账号);薄执行器只编排。
红线:只读采集 + 只写测试库;绝不碰发布。装进周 cron(见 scripts/install_cron.sh)。
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
    ap.add_argument("--real", action="store_true", help="强制真采集(覆盖 GY_METRICS_MODE)")
    ap.add_argument("--stub", action="store_true", help="强制 stub(覆盖 GY_METRICS_MODE)")
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    # **默认听 config.METRICS_MODE(GY_METRICS_MODE)**——2026-07-14 走运维流程发现:
    # 原来写死 `mode = "real" if a.real else "stub"`,**完全无视 config.METRICS_MODE**。
    # 于是 `GY_METRICS_MODE` 这个配置项存在于 config.py、注释写得清清楚楚,却**没有任何人读它**——
    # 运维照着注释在 .env 里设 GY_METRICS_MODE=real,以为切了真采,**实际跑的还是 stub 假数据**,
    # 而且他不会知道。跟 assert_publish_quota 是同一类病:东西造好了,没接线。
    mode = "real" if a.real else ("stub" if a.stub else config.METRICS_MODE)
    real = mode == "real"
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} mode={mode}"
          f"  (来源:{'--real' if a.real else '--stub' if a.stub else 'GY_METRICS_MODE'})")
    if not real:
        print("  ⚠️ stub 模式=**不真采、不写回**(零成本占位)。要真拿小红书数据:"
              "GY_METRICS_MODE=real 或加 --real", file=sys.stderr)
    s = collect.collect_and_writeback(mode=mode, limit=a.limit)
    if real:
        feishu_io.log_run(summary=f"回流 采集{s['采集']}写回{s['写回']}", action="回流")   # 记运行日志(复盘据此)
        if s["采集"] > 0 and s["写回"] == 0:   # 有已发却全采不到=疑登录态过期/取数挂→告警私聊
            from orchestrator import alerts
            alerts.send(f"回流全失败:{s['采集']} 条已发采集写回 0,疑登录态过期或取数挂", title="巧荷回流⚠️")
    print("采集写回:", json.dumps(s, ensure_ascii=False))
    # 复盘:按 playbook 聚合已发 note 效果(哪套方法论有效),喂周复盘/调权重
    fields = [r["fields"] for r in feishu_io.list_records(NF.TABLE)]
    print("按方法论复盘:", json.dumps(metrics.aggregate_by_playbook(fields), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
