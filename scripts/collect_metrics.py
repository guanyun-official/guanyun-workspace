"""回流采集薄执行器 CLI（每周一轮:采集互动数据 + 按 playbook 复盘)。

  python3 -m scripts.collect_metrics            # stub(零成本,不写;验结构)
  python3 -m scripts.collect_metrics --real     # xhs-extract-master 非登录真采集→写回测试库 + 复盘

采集能力是可替换 skill(xhs-extract-master 非登录,零封号不用我方账号);薄执行器只编排。
红线:只读采集 + 只写测试库;绝不碰发布。装进周 cron(见 scripts/install_cron.sh)。
"""
from __future__ import annotations

import argparse
import json

from orchestrator import collect, config, feishu_io, metrics
from orchestrator.bitable import NoteFields as NF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="真采集(默认 stub 零成本不写)")
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    mode = "real" if a.real else "stub"
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} mode={mode}")
    s = collect.collect_and_writeback(mode=mode, limit=a.limit)
    if a.real:
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
