# SourceOwnership：Base / workspace / skills 的唯一源边界

目标不是让 Base 和 workspace 保存两份再“对齐”，而是让每类信息只有一个 owner。非 owner 只能保存外键、运行状态、员工界面索引，或可重算的只读快照。

## 结论

| 信息 | Owner | 非 owner 可保留 | 禁止 |
|---|---|---|---|
| 账号注册表、账号名、小红书号、主页链接 | Base「账号表」 | workspace 文件名/frontmatter 的账号名作为指针 | workspace 另存小红书号、主页、上线事实 |
| 上线/停用、人工审批、发布状态、排期、效果数据 | Base | workspace 不保存 | git 文件里维护运行状态 |
| 账号画像、调性、受众理解、风格规律 | workspace `brands/<品牌>/accounts/{账号}.md` 正文 | Base 可有面向员工的摘要字段，但不得被引擎消费 | Base 作为生成画像权威 |
| strategy、cadence、autonomy、sourcing | workspace frontmatter | Base 可展示派生摘要 | Base 与 workspace 双写运营模式 |
| playbooks、内容切面、标题/正文公式、素材需求、生成 skill 指针 | workspace frontmatter `playbooks[]` | Base「内容类型表」只保留 tag、格式、所属账号 | Base「取数字段·切面」「文案元模版」作为权威 |
| 内容类型 tag、格式、所属账号索引 | Base「内容类型表」 | workspace playbook 用 `content_type` 引用 tag | workspace 维护员工筛选/关联关系 |
| skill 的“怎么做” | git skill 仓库 + `skills.lock.json` | workspace 只声明使用哪个 skill | 按账号/模式复制一份 skill |
| 素材文件、子素材视图、usage | 盘上素材库 / `lib/material_view` | Base 只存 Material/Note 投影字段 | Base 当媒体库或 usage 唯一源 |

## Skill 管理原则

Codex 不从语义上区分“自带 skill”和从 `guanyun-official/qiaohe-skill` 安装的 skill；区别只来自安装路径、锁文件和版本来源。因此本仓库的迁移/版本管理必须以 `skills.lock.json` 为唯一清单：

- 通用能力放在 qiaohe-skill / video-engine 这类 skill 仓库里，例如 `account-teardown`、`write-xiaohongshu`、`video-editing`。
- 账号差异、模式差异、内容公式不要做成每号一个 skill；放到 workspace 的 `playbooks[]`。
- playbook 只用 `gen_skill` 指向能力，不复制能力。
- `scripts/install_skills.sh` 只负责按 lock 安装/重装；安装产物是易耗缓存。

推荐的 skill 仓库结构是能力分层，而不是账号分层：

```text
qiaohe-skill/
  common/                 # 通用采集、拆解、写作、质检能力
  xhs/                    # 小红书平台手脚
  qiaohe/                 # 巧荷领域通用能力，不按账号拆
  video/                  # AI 剪视频/分镜/物化能力；也可独立 video-engine 后由 lock 引用
```

账号/模式目录应留在 workspace：

```text
brands/观云/accounts/{账号}.md
  frontmatter.playbooks[] # 每账号每模式的 data
  body                    # account-teardown 产出的账号画像
```

## 测试 Base 重构规则

测试/运营 Base 可以按目标重构，不保留沉没成本。但每次重构必须满足：

1. 生产 Base 禁写。
2. 先把 owner 规则写进 workspace 和审计，再改测试 Base。
3. Base 字段若不再是 owner，优先清空运行数据里的内容；字段本身可暂留到迁移清单处理，避免 schema diff 无上下文扩大。
4. `scripts/account_kernel_audit.py` 必须无 FAIL。
5. `scripts/ar_check.py` 必须保持 100。

## 当前决策

`内容类型表` 的 `取数字段·切面` 与 `文案元模版` 不是 Base owner；这些 know-how 已迁入 workspace `playbooks[]`。Base「内容类型表」只作为员工选择 tag 与格式/账号索引。
