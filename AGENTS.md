# AGENTS.md · 观云 Workspace 环境事实

> 任何 agent(Claude Code / Codex / headless)进入本仓库先读这份。搭建计划与阶段验收见 `docs/PLAN.md`。
> 方法论一句话:**飞书当脸,CLI agent 当手,Bitable 当账本,git skills 当大脑,人当质检员和发布键。**

## 六角色一览

| 角色 | 承担者 | 铁律 |
|---|---|---|
| 账本(唯一真相源) | 飞书 Bitable 生产 Base(见下) | 一条内容一行,状态列是唯一真值;不当队列、不当媒体库 |
| 大脑(能力) | git 技能仓库(qiaohe-skill、video-engine),经 `skills.lock.json` 安装 | 只装"怎么做";实例配置一律外置注入 |
| 手(执行壳) | Claude Code 主力,Codex 备用 | 易耗品,双入口,换壳成本趋近零 |
| 推进器(loop) | 本仓库 `orchestrator/`(cron + webhook + heartbeat,P4) | 自身零 LLM(纯确定性路由);单实例串行 |
| 脸(员工界面) | 飞书原生:表单/看板/仪表盘/审批卡片 | 员工永不直接碰 agent |
| 人 | 拍素材、审内容、点发布(勾 AI 声明) | 两个人审硬门不可自动化 |

## Base 事实

- **生产 Base(巧荷 Qiaohe-official-beta)**:`N9IVbi6pTatJG5sqyTTcc0vSn4g`,共 14 表。
- **测试 Base**:`ZhzJbfkOsafwevsWkW8cfoILnfb`(曾复制自生产；2026-07-10 起按 SourceOwnership 重构为新体系工作台,当前 13 表,不再追求生产 14 表保真)。
- **默认一切写操作只进测试 Base**(`.env` 的 `LARK_APP_TOKEN` 默认=测试 Base;`TEST_MODE=1`)。
  生产 Base 只读(dump schema 等);生产变更一律走"迁移清单 + 人工确认"(见 docs/PLAN.md P7)。
- 旧观云 Base `ITz4bsLSWaKuSqsuUaocmEC0nXe` 已废弃,不纳入 schema 管理。

### 生产 Base 14 表 table_id 清单(2026-07-08 lark-cli 实拉)

| 表名 | table_id |
|---|---|
| 衣服总表 | `tbl2ZnYoLX3d0QtE` |
| 账号表 | `tblveO3Wzm3Foo6v` |
| 内容类型表 | `tblWZgMpWNqfHabt` |
| 面料·工艺库 | `tbljjcr9gLk7cPbn` |
| 素材表 | `tbles5eiDykCBxD1` |
| 笔记表 | `tblHi1Htg5wntydY` |
| 关键词库 | `tblaiG8bQumH5CQW` |
| 目标客户 | `tblM6EDqDdcPYIxO` |
| 灵感库 | `tblP4jlRNZGCiIU2` |
| 技能表 | `tblSidOqOT1B4dj9` |
| Issue 表 | `tblcvycKVdY3IF7A` |
| 修订日志 | `tbleWyxtJD57a59X` |
| 素人推广案例 | `tblj8q46icA5YZoM` |
| 运行日志表 | `tblgZRFvZiZtfxNN` |

> 字段级契约(field_name/type/select 枚举)在 `schema/prod/<表名>.json`(`scripts/dump_schema.py` 产出);
> 测试 Base 契约 dump 到 `schema/test/`。**测试 Base 的 table_id 与生产不同**,且测试 Base 可为验证新体系删表/删字段；写代码取表一律按表名经 schema 解析,不硬编码 table_id。

## 小红书账号(4 个;**以账号表 `tblveO3Wzm3Foo6v` 为准**,此处仅快照)

| 账号 | 备注 |
|---|---|
| `63068651425` | 小红书号 |
| `26507264096` | 小红书号 |
| `60befdfd000000000101cc10` | user id |
| 官号 @巧荷·东方美学 | 品牌官号 |

## 红线(所有 agent 必须遵循)

- **绝不自动发布**:AI 只做到"待发布包",人手机发布并**必勾 AI 声明**(《AI 生成合成内容标识办法》2025-09 生效;小红书 2026-02 强化公告)。
- **单号 ≤3 篇/天**,间隔 ≥2h + 随机延迟;多号内容强差异化(账号表调性字段 + 内容类型元模版注入)。
- **防搬运**:爆款只当情报,产出绝不含原帖原文片段(出口闸把关,`lib/skill_gate.no_source_leak`)。
- **Bitable 单 writer 串行 + 429 退避 + 业务键幂等**;自动化只挂关键状态。
- **素材库约定**:大文件走本地素材库 + 表存相对路径,目录 `素材库/{SKU}/01-原始拍摄|02-AI生成|03-成片|04-工作台`,命名 `{SKU}-{排期编号}-S{n}_{AI|实拍}.mp4`;搬家只改根前缀。
  - **生成媒体同拍摄媒体,一视同仁走盘**:AI 生成图/草稿落 `02-AI生成`、最终成片落 `03-成片`;素材表 `链接`(text) 存相对路径、`来源`=AI生成、`生成参数` 记 prompt/模型。**Bitable 不当媒体库**——成片视频/高清图这类大文件绝不进表;`文件`(attachment) 字段只放能在飞书直接预览的小图。无数据盘时就本地,将来迁 NAS/对象存储只改根前缀。
- 密钥只存 `.env`(不入库),泄漏即在飞书后台/各平台轮换。

## 工具清单

| 工具 | 用法/注意 |
|---|---|
| `lark-cli` | 飞书读写统一走它。**一律 `--as bot`(璃奈,app `cli_a965851065381ccb`)+ `LARK_CLI_NO_PROXY=1`**(宿主机代理会弄挂它)。gotchas:`+record-get` 字段直接挂 `data.record` 下;`+record-delete` 要 `--yes`;建带 property 字段走 bitable v1,公式走 base v3 |
| `hermes` | 飞书消息网关(告警/日报投递) |
| `ffmpeg` | 视频直出成片(video-editing 技能的基座之一) |
| VectCutAPI | `:9001` 本地服务,剪映草稿物化(video-editing);P4b 起 launchd 守护 |
| `.mcp.json` | MCP 连接器声明(密钥按名引 env);当前为空骨架,后续接 xiaohongshu-mcp 等 |

## 仓库结构

```
guanyun-workspace/
├── AGENTS.md            # 本文件:环境事实(Codex/CC 通用)
├── CLAUDE.md            # → 薄指针指向本文件
├── .mcp.json            # MCP 连接器声明(最小骨架)
├── .env.example         # 全量 env 键说明;真值在本地 .env(不入库)
├── schema/              # Bitable 字段契约(prod/ + test/ + snapshots/)
├── skills.lock.json     # 技能安装清单(锁 repo+sha+skills)
├── skills/              # install_skills.sh 产出的 symlink(不入库)
├── scripts/             # dump_schema.py / install_skills.sh / check_p1.sh
├── orchestrator/        # 推进器(P4,未建)
├── lib/                 # seams:feishu_workbench/xhs_fetch/apify_xhs/brand_kb/skill_gate/skill_io
├── brands/              # 品牌静态资产(自 AI-marketing 迁入)
└── docs/                # PLAN.md 等
```

## 开发 or 运营?（先读 docs/运行模式.md）
- **运营环境 = 测试库 `ZhzJbf…`**(当前 .env + TEST_MODE=1 即上线态);生产库 `N9IVbi…` 焊死不碰。**"上线"= 在测试库挂 cron,不是切生产库。**
- 改系统 → 开发 loop(check_p* 全绿 + ar_check 100 + issue 清零);跑内容 → 运营 loop(`install_cron.sh --install`)。

## 架构现状（2026-07-09，内容工厂全链闭合）

领域词汇见 `CONTEXT.md`,素材视图层设计与评审见 `docs/架构演进-素材视图与方法论.md`。要点:
- **Playbook(方法论)** = 账号 strategy `playbooks[]`,一号可多套;每套 = 配方(切面/权重/material_needs/公式) + `gen_skill`(产这套笔记的技能) + `view`(素材视图键)。`orchestrator/accounts.playbooks_of/resolve_playbook/gen_skill_of`;显式优先,否则从 content_mix 合成。
- **素材视图层(盘上,非 Bitable)** = `lib/material_view`:每 playbook 一套软链 bin;子素材 **Clip**,`clip_id=哈希(素材编号,span)` 稳定(文件搬家 `relink` 不断链);**usage 账本 `_usage.jsonl` = usage 唯一真值**;linked%/used% 使用率;`trace_note` 回溯。`ingest select/view/summary/trace` 是 agent 编入/查看/回溯的 CLI。
- **闭环**:planner **view-驱动「今日发」**(SKU 可选,`scripts/planner.py`) → daily 经 `materialize_day` 用稳定业务键幂等创建 Note；只有原料、仍需「AI剪」的候选进入 `orchestrator/media_processing.py` 的盘上 MediaTask，停在 `待生成剪单/剪单待人确认/成片待验收` 等人审门，只有 `可建 Note` 的最终 Material 才回到 Note 状态机 → 按 playbook 配方+gen_skill 生成(`orchestrator/llm.gen_copy`) → 发布回填 usage(engine `MARK_PUBLISHED` 读「关联子素材」clip_ids) → `COLLECT_METRICS` 经 **xhs-extract-master 非登录采集**(`orchestrator/metrics`,默认 stub 零成本)写回 点赞/收藏/评论/转发 → `aggregate_by_playbook` 反馈进排产。
- **测试库已加字段(生产库未动)**:运行日志表 `成本_元`(number)、笔记表 `方法论`+`关联子素材`(text)。**加测试库字段流程**:`lark-cli base +field-create`(读回自证)→ `dump_schema.py --base test` → 登记 `bitable.py` 字段常量 + `scripts/schema_diff.py` 的 `P2_EXPECTED`(反漂移白名单)。
- **反漂移契约锁三层**(名字/取值/类型,`tests/test_field_contract.py`)+ 状态漂移告警。硬门:6 个 `check_p*.sh` + `ar_check`=100 + 单测全绿。加能力必带测试。
