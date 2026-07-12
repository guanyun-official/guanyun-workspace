# AGENTS.md · 观云 Workspace 环境事实

> 任何 agent(Claude Code / Codex / headless)进入本仓库先读这份。搭建计划与阶段验收见 `docs/PLAN.md`。
> 方法论一句话:**飞书当脸,CLI agent 当手,Bitable 当账本,git skills 当大脑,人当质检员和发布键。**

## 六角色一览

| 角色 | 承担者 | 铁律 |
|---|---|---|
| 账本(唯一真相源) | 飞书 Bitable 生产 Base(见下) | 一条内容一行,状态列是唯一真值;不当队列、不当媒体库 |
| 大脑(能力) | git 技能仓库(qiaohe-skill、video-engine),经 `skills.lock.json` 安装 | 只装"怎么做";实例配置一律外置注入 |
| 手(执行壳) | Claude Code 主力,Codex 备用 | 易耗品,双入口,换壳成本趋近零 |
| 推进器(loop) | 大刀阔斧后=薄执行器 `orchestrator/draft.py`(按需/手动跑;数据备份+周复盘走 cron,内容 cron 待轻调度器见 #8) | 只推到草稿待发,绝不自动发布 |
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
├── scripts/             # draft_one.py(薄执行器CLI)/ ingest.py / dump_schema.py / install_skills.sh / check_p*.sh
├── orchestrator/        # 薄执行器 draft.py + 已验证原语(accounts/llm/guard/feishu_io/bitable/config/metrics/alerts/skills_lock)
├── lib/                 # ⚠️技能层共享运行库,非死码——qiaohe-skill 的 Python 技能(立号/爆款拆解/选题深化)
│                        #   经三级路径定位(parents/…/lib)注入 sys.path 后 import:feishu_workbench 写库/
│                        #   xhs_fetch 取数/skill_gate 校验+防搬运/skill_io I/O契约/brand_kb 品牌注入(apify_xhs 供 xhs_fetch)。
│                        #   orchestrator 不 import 它(两个独立子系统,各有一套写库/取数/防搬运),但删了会断技能层(check_p3⑥ 会红)。
├── local-skills/        # 号/模式特化 skill(writing-{amateur-ootd,ootd-caption,brand-newpiece};compose 通用+真实帖 few-shot)
├── brands/              # 账号声明·画像 + knowledge_base 内容 know-how(衣服考据)
└── docs/                # 交接文档.md(权威)/ 架构与方法论.md / PLAN.md 等
```

## 开发 or 运营?（先读 docs/运行模式.md）
- **运营环境 = 测试库 `ZhzJbf…`**(当前 .env + TEST_MODE=1 即上线态);生产库 `N9IVbi…` 焊死不碰。**"上线"= 在测试库挂 cron,不是切生产库。**
- 改系统 → 开发 loop(check_p* 全绿 + ar_check 100 + issue 清零);跑内容 → 运营 loop(`install_cron.sh --install`)。

## 架构现状（2026-07-11，大刀阔斧后·薄执行器骨架）

领域词汇见 `CONTEXT.md`;方法论见 `docs/架构与方法论.md`;权威依据 `docs/交接文档.md`。
重引擎(engine/planner/推进器)、素材视图层(material_view/Clip/usage)、契约锁三层、审计工具(account_kernel/base_workbench)已删(净删~4000行,git history 可查)。要点:
- **薄执行器 `orchestrator/draft.py`**(CLI `scripts/draft_one.py`)= 体系核心:读账号声明 → 取该号 playbook 的 gen_skill → `load_gen_skill` 加载其 `SKILL.md` 真实帖 few-shot → 组稿(画像+few-shot+配方)→ 过 base 红线闸 → 写笔记表「草稿待发」。stub 默认零成本,`--llm real` 走 `llm.run_prompt` 预算帽。**只推到草稿待发,绝不代勾 AI 声明、绝不自动发布**;发布与 AI 声明是人手。第一目标 A 已真跑通(ootd号 真出可发草稿,4 号泛化验证过)。
- **已验证原语**(§5 移植保留):`feishu_io`(lark-cli api 底座)、`guard`(红线闸:只写测试库/AI声明门/控量)、`accounts`(声明加载)、`llm.run_prompt`(real 生成)、`bitable`(字段词汇 + text/parse_ts/link_record_ids 多形态收窄函数)、`metrics`(extract 采集 xhs-extract-master 非登录,默认 stub)、`alerts`(hermes 薄网关)、`ingest`(scan/link/register 素材摄入)。
- **playbook 指向 gen_skill,gen_skill 是 skill**(特化住 `local-skills/`、通用在 qiaohe-skill remote);`skills.lock.json` 按 source(remote/local)统一管。加发法=写 playbook 声明 + 建 gen_skill,**不改 schema**。
- **加测试库字段流程**:`lark-cli base +field-create`(读回自证)→ `dump_schema.py --base test` → 登记 `bitable.py` 字段常量。漂移检测用 `dump_schema + git diff schema/test`(git 兜底)。
- **keep 门**:6 个 `check_p*.sh`(p2 测试库健康 / p4 薄执行器 A 验收 等)+ `ar_check`(12 项精简痛点:A可跑 / few-shot 真进 prompt / 唯一源 / 红线…)=100 + 单测全绿。加能力必带测试。
