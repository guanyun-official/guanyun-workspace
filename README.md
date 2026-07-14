# guanyun-workspace

巧荷内容工厂的 **harness** —— 给模型双手、双眼、知识和法律的那个仓。

> **Agency 来自模型。Agent 产品 = 模型 + Harness。**
> **我们不"开发 agent",我们造 harness。造好 harness,模型会完成剩下的。**

```
Harness = Tools + Knowledge + Observation + Action Interfaces + Permissions
```

**Agent 是模型**(做一切判断)。**Base / 网盘 / 小红书是世界**(状态 · 唯一真源),不属于 harness。

## 进门读什么

| | |
|---|---|
| `CLAUDE.md` | **心智 · 唯一判据 · 红线 · 实测纪律**(每轮自动进上下文) |
| `AGENTS.md` | 环境事实:Base / 账号 / 凭证 / 工具 / 仓库结构 |
| `docs/架构.md` | **全景图** · 技能是 Knowledge 不是函数 · **欠账(唯一一份)** · **进化回路** |
| `docs/踩坑账.md` | **唯一一份病例**:形态陷阱 / 人面缺陷 / 检查器自己得了它要抓的病。已定的事别翻案,要翻先改这份 |
| `CONTEXT.md` | 领域词汇(给 seam 起名) |
| `docs/上岗包.md` | **给服务器数字生命的交接**:手/眼/法/知识清单 · 自主边界 · 上岗流程 |
| `docs/培训包.md` | **上岗前的考核**:三段漏斗 · A/B/C/D 考核 · 合格的样子长什么样 |

## 红线

**只写测试库 `ZhzJbf`**(生产库读也不碰)· **绝不自动发布** · **绝不代勾 AI 声明** · **红线不许有旋钮**

## 门

```bash
bash scripts/review_gate.sh --full   # 红线测试 + schema契约 + 技能真源同步(sha对GitHub) + 真库冒烟(board) + 备份
```

**门只留两种:对账**(代码 vs 活库 · lock sha vs GitHub)**和真跑**(board 真跑 · 备份真做)。
**审查是子 agent 的活,不是脚本**(机器审自己会得它要抓的病 —— 见 `docs/架构.md` 第六节)。
**全绿才提交。红=不留。**

## 运营

运营库 = 测试库 `ZhzJbf`(当前 `.env` 即对;**`TEST_MODE=1` 本身就是上线态**)。
**"上线" ≠ 切生产库**(生产库焊死不碰)。

**心跳由 agent 自己管** —— harness 给它 shell(能读写 crontab、能订阅事件);
**几点醒、醒来干什么,是它的判断**。人只需说一句「每天早上看看有没有活」。

## 技能

唯一真源 = `qiaohe-skill` 仓。`skills/` 是 `install_skills.sh` 按 `skills.lock.json` 装出来的符号链接(不入库)。
**workspace 不藏技能。**

```bash
bash scripts/install_skills.sh
```

## .mcp.json

当前是最小合法骨架(`{"mcpServers": {}}`)。后续声明 MCP 连接器时,**密钥一律按名引用 env**,真值只存本地 `.env`。
