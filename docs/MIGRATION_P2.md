# MIGRATION_P2 — 历史迁移清单（不属于当前上线流程）

> 历史背景：这份清单原用于“测试 Base 变更 → 生产 Base 应用”。2026-07-09 用户已澄清：
> **上线 = 在运营库/测试库 `ZhzJbfkOsafwevsWkW8cfoILnfb` 挂 cron，不切 `N9IVbi`，不改 `TEST_MODE=0`。**
> 因此本清单只保留为审计资料，不作为当前上线步骤。生产 Base `N9IVbi6pTatJG5sqyTTcc0vSn4g` 当前只读、焊死不碰。
> 原则：只加不删；单选 PATCH 必须回填现有 option 的 `id`（只追加新 name），否则会重建选项、破坏既有记录引用。

## 变更项（与测试 Base 对齐）

1. **笔记表.状态 追加 3 个选项**：`已批准`、`待发布`、`已回流`
   - 步骤：GET 该字段 raw property → options 列表保留原 6 项（含 id）→ 末尾追加 3 个 `{"name":...}` → PATCH（bitable v1 fields）。
   - 生产的 option id 与测试不同，**绝不能照抄测试的 id**。
2. **笔记表 新增字段 `AI声明`**：checkbox（type 7）。
   - POST /open-apis/bitable/v1/apps/{prod}/tables/{笔记表}/fields `{"field_name":"AI声明","type":7}`
3. **账号表核对 4 个账号标识**（缺则补，不覆盖已有）：
   - 科普号：小红书号 `63068651425`
   - （待核名）：小红书号 `26507264096`
   - 巧荷｜OOTD：主页链接 `…/user/profile/60befdfd000000000101cc10`
   - 官号@巧荷·东方美学
4. **自动化（UI 手工，见 P2_手动配置清单.md）**：自动化不随 Base 复制、无创建 API——生产上需在 UI 重新配置（测试 Base 验证过的同款）。

## 状态机语义（应用后全链）

`想法储备 → 待拍素材 → 待出文案 → 草稿待发(=待审) → 已批准 → 待发布(发布包就绪,等人发) → 已发 → 已回流(效果数据已回填)`；`暂缓归档` 为旁路状态。AI 声明 = 发布包完整性门的一部分（未勾不得进"待发布"）。

## 验证（应用后立即执行）

```bash
python3 scripts/dump_schema.py --base prod
python3 scripts/schema_diff.py schema/snapshots/prod-切换前-<日期> schema/prod --assert-p2
# 再建一条 _TEST-MIG 记录走 草稿待发→已批准→待发布 后删除（同 P2 实测）
```

## 回滚

- 3 个状态选项与 AI声明 字段：**在无记录使用它们时**可直接删（DELETE field / PATCH 去掉 option）；已有记录引用后不回滚，只停用（视图不暴露）。
- 快照目录即字段级恢复依据。
