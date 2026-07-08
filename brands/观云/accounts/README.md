# 账号画像层(每号一份 data,不是每号一个 skill)

**方法论拆两半**:「怎么从已有内容总结账号风格」= 可复用 skill(`account-teardown`);「这个号具体什么风格」= 每号一份画像(本目录),生成时注入。

- 文件名 = 账号表里的账号名(如 `科普号.md`)。
- 内容 = account-teardown 对该号近~20篇的 6 维总结 + 素材利用偏好。**由 skill 填充,不手编**(占位可先写,拆解后覆盖)。
- 消费方 = `orchestrator/llm.py` GEN_COPY 按笔记的账号(自动)加载对应画像注入提示词 → 生成贴该号既有风格。
- 更新 = 每号内容风格漂移时重跑 account-teardown 覆盖(git 可回溯)。

**红线**:画像里只存**可迁移打法/风格规律**,绝不存原帖文案片段(防搬运,与 account-teardown 出口闸一致)。

## 账号模式 = 声明式 strategy(泛化,非一模式一脚本)

每号一个 `{账号}.strategy.json` 声明其运营模式(cadence 缓发节奏/material_needs 素材需求/autonomy 自主程度/sourcing 素材来源)。
`scripts/planner.py` 是**通用解释器**:读任意账号 strategy → 算 缓发+余量+催拍,**引擎零账号特定代码**。
**加新账号/改模式 = 写/改 strategy JSON,不动代码。** 模式举例:考据慢发(科普号)/集中拍上身+缓发(ootd号)/实验号手动(玉子)/品牌叙事低频(官号)。
三层:能力=skill(怎么做) · 模式=strategy(每号怎么运营,data) · 引擎=planner+orchestrator(读声明执行,泛化)。
