# ADR-0001 · Base schema 全面审查(对齐 loop)

- 日期:2026-07-11
- 状态:已决
- 背景:用户要求整个 base 按最新精神(薄执行器 + 不分衣服/材质 + 五唯一源 + 老板员工全流程)逐表逐字段审,留/砍/调,并判是否缺表/缺字段。

## 决策:10 表定型(14→10),字段类型已对,无需新表

### 已砍(4 表,legacy)
| 表 | 为什么砍 |
|---|---|
| 技能表 | skill「怎么做」归 git 技能仓库 + skills.lock,base 不当 skill 目录 |
| 修订日志 | 早期手工文案迭代 cruft,pre-system,人审现在在草稿待发门做 |
| 衣服总表 | **不分衣服**:衣服 know-how(卖点/形制/文物出处/纹样)已迁 workspace `knowledge_base/衣服/`,身份字段薄执行器不用 |
| 面料·工艺库 | **不分材质**:面料/工艺是内容 know-how,科普说明本就空,归 workspace |

### 留(10 表,各有唯一源角色)
| 表 | 角色(owner) | 审查结论 |
|---|---|---|
| 笔记表(23字段) | Note 状态机 + 效果数 + 发布回填 | 留。点赞/收藏/评论/转发/新增关注**已是 number**(lark-cli API 回读成字符串是其怪癖,已由 metrics._num 吃字符串修掉);热度分 formula 正常算 |
| 账号表(13) | 账号注册表 | 留。workspace_ref=指针、投手=员工分工、上线状态=运营事实 |
| 内容类型表(5) | 内容 tag registry | 留(已瘦到 tag 三件套+启用/展示) |
| 素材表(13) | 素材投影(按赛道·不挂衣服) | 留(§4 已去关联衣服/面料) |
| 运行日志表(15) | 运营观测(成本/动作) | 留。engine 时代列(automation_id/run_id/duration_ms/error_type/数据用途)现无写入=可后续瘦,但属观测 infra,defer |
| 灵感库(15) | 员工界面·灵感表单 + 爆款拆解情报 | 留(老板员工全流程:员工提灵感→转化为笔记) |
| Issue 表(13) | 点对点需求 lane | 留(员工提需求→产物落回,§4 明列) |
| 关键词库(8) | tag registry | 留(笔记表·标签·关键词 link 消费) |
| 目标客户(9) | 采集情报(受众挖掘输出) | 留(xhs-audience-miner skill 产) |
| 素人推广案例(11) | 素人合作运营数据 | 留(合作状态/授权/转化=运营事实,qiaohe-amateur-miner skill 产) |

### 缺表/缺字段判断:不缺
老板员工全流程(员工提需求→摄入→产→审→发→回流→复盘)所需落表都在:
- 排期 = 笔记表·计划发布日(人定,无需 planner 排产表)。
- 素材加工(AI剪)= 调 video-editing skill,成片落素材表(来源=AI生成),无需 MediaTask 表(加能力不改 schema)。
- 复盘 = metrics.aggregate_by_playbook 从笔记表效果数**现算**,无需复盘表(将来要趋势历史再议)。

## 后续可选(非阻塞,defer)
- 运行日志表 engine 时代列瘦身——等 draft/collect 接 log_run 观测时一并定。
- 账号表 画像状态/画像更新时间(画像 owner 是 workspace)——面向员工摘要,SOURCE_OWNERSHIP 允许,留。

## 影响
- keep 门:98 单测 / ar_check 100(14项)/ 6 check_p 全绿。
- 权威:`CONTEXT.md「唯一源边界」` + `docs/架构.md`。
