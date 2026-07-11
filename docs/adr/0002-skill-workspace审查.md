# ADR-0002 · Skill 与 Workspace 审查(对齐 loop 收口)

- 日期:2026-07-11
- 状态:已决
- 背景:对齐 loop 除 base(ADR-0001)外,skill 与 workspace 两层也逐一审对齐。

## Skill 审查:24 个对齐,覆盖全流程,无需增删

`skills.lock.json` = 唯一清单,与 `skills/`(24 symlink)一致:
- **remote qiaohe-skill(18)**:采集 xhs-extract-master、爆款拆解 explosive-teardown、立号 account-teardown、
  miners(qiaohe-amateur-miner→素人推广案例、xhs-audience-miner→目标客户)、需求(feishu-requirement-manager/issue-tracker)、
  写作(write-xiaohongshu/content-writing/guanyun-OOTD-text…)、平台(xiaohongshu/-images/-cover/-note-analyzer)、topic-deepening、xhs-collector、searxng、qiaohe-video-script。
- **remote video-engine(3)**:video-editing(剪辑)、video-storyboard、video-previz。
- **local 特化(3)**:writing-{ootd-caption,amateur-ootd,brand-newpiece}——compose 通用 + 该号真实帖 few-shot,description 第三人称。

结论:gen_skill(3 local)+ 采集 + 剪辑 + 爆款拆解 + miners + 需求 都在,**覆盖老板员工全流程每环**。remote 写作类有部分功能重叠,但属独立仓库可复用能力(local 特化 compose 之),不删。加能力=加 skill 不改 schema。

## Workspace 审查:薄执行器骨架 lean,声明健康,文档对齐

- **薄执行器模块**:draft/collect/ingest/accounts/llm/guard/feishu_io/bitable/config/metrics/alerts/skills_lock——全在用,无死码(gen_copy/engine/planner/runbook/material_view 已删)。
- **账号声明·画像**:4 号 frontmatter 全可解析(accounts.problems 空),画像正文对齐实抓校正。
- **knowledge_base**:衣服 know-how(GY-001/002/003)从 base 迁入,写考据用。
- **文档**:AGENTS/CONTEXT/README/架构与方法论/运行模式/架构一图流 全对齐薄执行器现实;TARGET_INVENTORY/架构演进 加了废弃横幅。

## 对齐 loop 结论
base(10表·ADR-0001)/ skill(24·本ADR)/ workspace(薄执行器骨架·本ADR)三层都按最新精神对齐,决策可追溯。
→ 转**真实验证 loop**:全真实无 stub、派 subagent 扮演老板/素材拍摄者/投手、生产级压测 + 老板员工全流程贯通。
