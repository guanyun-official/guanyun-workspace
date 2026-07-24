# scripts/cron/

这是 monitor cron 的**预检查脚本**(probe),Hermes cron 用 `--script` 挂载。

## 用途

每次 monitor cron 触发时先跑这个脚本(零 LLM 成本,~1.3s):
- 没变化 → stdout 打印 `NO_CHANGE`,prompt 指示 agent 立刻 `[SILENT]` 退出
- 有变化 → stdout 打印新/变更记录摘要,agent 据此处理

这样空转从「完整 agent 一醒一思考」降到「一次短 API 调用 + 1 条超短 LLM 回合」。

## 部署

脚本真身在仓里 `scripts/cron/*.py`,上线时拷到 `~/.hermes/scripts/`(hermes cron `--script` 只认这个目录):

```bash
cp scripts/cron/qiaohe_monitor_*.py ~/.hermes/scripts/
```

## monitor

| Job | 脚本 | 调度(已压到工作时段) | 原调度 |
|---|---|---|---|
| qiaohe-monitor-status | qiaohe_monitor_status.py | `0 * 9-22 * * *` (14/天) | `*/15 * * * *` (96/天) |

总唤醒:35/天(原 168/天,降 79%)。空转的大部分被 `NO_CHANGE` 短路。

## 游标

每个脚本在 `~/.hermes/state/qiaohe-last-*-{cursor,ts}` 存上次处理过的最新 record_id/时间戳,幂等。删了就从最新一页重放(只会重复处理最多一屏,不会丢事件)。

## 终局

这是 poll 的兜底方案。真·事件驱动走飞书 webhook,等公网入口配好后把 cron 改成 `schedule=webhook:qiaohe-base`,poll 脚本保留当兜底心跳(间隔拉到 6h)。

> ⚠️ 这行原先写着"见 **Issue 表**「启用 webhook 事件驱动」" —— **那张表作废了**(2026-07-17)。
> 问题的台账是 **GitHub Issue**(`guanyun-official/guanyun-workspace`),见 `evolving-the-system` 技能。
> 这条 webhook 待办没进 GitHub Issue —— **想做的时候自己提一条**,别去 base 里翻。
