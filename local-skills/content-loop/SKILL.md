---
name: content-loop
description: 观云内容推进器——读飞书笔记表状态,按 runbook 路由动作(排产/生成/催拍/催审/发布检测/回流),硬闸焊代码里(AI声明门/单号控量/月成本熔断/Base守卫)。引擎自身零 LLM,LLM 只在 GEN_COPY 动作内经预算帽调用。cron/heartbeat 触发或人工跑。触发词:跑推进器/排产/每天发什么/内容loop/heartbeat。
license: MIT
---

# content-loop · 内容推进器（引擎作为可挂载 skill，候选B）

> 这是"怎么跑内容 loop"的能力封装(SKILL.md=给 LLM/人的入口)+ 捆绑确定性脚本(硬闸/幂等,零 LLM 执行)。
> 挂载本 workspace 后即可用;换壳(Claude Code/Codex/cron)姿势一致。

## 接口（窄，稳定）

```bash
# 推进一轮(读表→route→执行→写回+运行日志)。单实例(flock),自身零 LLM。
python3 -m orchestrator.run --mode daily      --llm stub   # 每日排产轮+日报;--llm real 才真花钱生成
python3 -m orchestrator.run --mode heartbeat  --llm stub   # 巡检轮(催拍/催审/发布检测/回流)

# 每号今天发什么(缓发排产+素材余量+催拍);读账号 strategy,只读不写
python3 scripts/planner.py [--account 科普号]

# 素材摄入(乱素材→agent看懂→软链上墙原件不动→挂SKU登记素材表)
python3 scripts/ingest.py scan <目录>
python3 scripts/ingest.py link <文件> <SKU> <类目> [名]
python3 scripts/ingest.py register <SKU> <编号> --type <类型> --link <软链> --sku-link <衣服编号>
python3 scripts/ingest.py orphans                          # 列未挂SKU素材待补
```

## 红线（焊在脚本里,LLM 绕不过）
- **AI声明门**:进"待发布"前必须 AI声明=true,否则拒绝告警。
- **单号控量**:单号每日发布上限(默认3),超额拒绝。
- **月成本熔断**:LLM 月成本超阈本轮停止生成。
- **Base 守卫**:TEST_MODE=1 只许写测试 Base,生产 Base 物理够不着。
- **绝不自动发布**:引擎只做到"待发布包",人手机发布并勾 AI 声明。

## 何时触发
- cron 每日 09:00 `--mode daily`;工作时段每30分 `--mode heartbeat`(见 scripts/install_cron.sh)。
- 员工上传新素材后 `ingest`。
- 人只做:挂 SKU/素材 + 审批(飞书翻状态列)。

## 依赖
挂载 workspace(含 orchestrator/、scripts/、brands/、schema/、.env)。字段访问经 orchestrator/bitable.Record(候选A);账号模式经 orchestrator/accounts(候选C)。
