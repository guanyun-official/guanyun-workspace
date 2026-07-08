# 多品牌接入指南

> 一个品牌 = `brands/<brand_id>/` 下一份数据（**品牌库**，见 `../CONTEXT.md`）。

> ⚠️ **2026-06-22 架构重构后,本文部分内容待更新。** 旧 pipeline 体系已弃用(见 `../docs/adr/0003`):
> `pipelines/` 目录与旧 `run_a1.py` 跑法已**删除**;`lark_config.pipeline_tables` 已收敛为
> **`review_tables`**(待审表),由 `lib/feishu_workbench.py`(飞书工位/ADR-0002)消费;`formulas.*.applicable_pipelines` 仅剩历史标记。
> 当前模型的品牌库 = `profile.json` / `formulas/` / `lark_config`(base/review_tables/public_tables/states) / `knowledge_base/`。
> 下文按旧 pipeline 写的"4 管线配置 / run_a1.py 跑法"段落已过时,接新品牌只参考静态资产部分。

---

## 1. 目录结构

```
brands/<brand_id>/
├── profile.json              # 品牌档案（必填）
├── lark_config.json          # 飞书配置（必填）
├── formulas/                 # 公式库（必填）
│   ├── title_formulas.json
│   ├── body_formulas.json
│   ├── visual_formulas.json
│   └── modification_principles.json
├── pipelines/                # 4 管线配置（必填）
│   ├── A1.json
│   ├── A2.json
│   ├── A3.json
│   └── B.json
├── assets/covers/            # 本地封面图（可选，飞书上有同一份）
├── knowledge/                # 品牌知识库（可选）
├── products/                 # 产品档案原始数据（可选）
└── notes/                    # 临时 notes（可选）
```

---

## 2. profile.json 必填字段

```json
{
  "brand_id": "新品牌ID",
  "profile": {
    "name": "新品牌名",
    "slogan": "品牌slogan",
    "positioning": "一句话定位",
    "tone_keywords": ["调性1", "调性2"],
    "visual_guidelines": {
      "style": "视觉风格描述",
      "color_palette": ["#hex1", "#hex2"],
      "forbidden_colors": ["#禁用1"]
    },
    "accounts": [
      {
        "account_name": "账号名",
        "track": "赛道",
        "xhs_account_id": "小红书账号ID（可选）"
      }
    ]
  },
  "principles": [
    "原则1：禁用'汉服'表述",
    "原则2：标题 < 25 字",
    "原则3：单条笔记不超 1000 字"
  ],
  "forbidden_words": ["禁用词1", "禁用词2"]
}
```

---

## 3. lark_config.json 必填字段

```json
{
  "base": {
    "name": "新品牌飞书 Base",
    "app_token": "飞书 app_token",
    "url": "飞书 base URL"
  },
  "public_tables": {
    "brand_master": {"name": "品牌主档", "table_id": "tblxxx"},
    "brand_insights": {"name": "品牌内核库", "table_id": "tblxxx"},
    "product_catalog": {"name": "产品档案", "table_id": "tblxxx"},
    "asset_pool": {"name": "资产池", "table_id": "tblxxx"},
    "explosive_library": {"name": "爆款库", "table_id": "tblxxx"}
  },
  "pipeline_tables": {
    "A1": {"name": "A1_全自动内容", "table_id": "tblxxx", "skill": "pipeline-A1"},
    "A2": {"name": "A2_指定爆款", "table_id": "tblxxx", "skill": "pipeline-A2"},
    "A3": {"name": "A3_指定风格", "table_id": "tblxxx", "skill": "pipeline-A3"},
    "B":  {"name": "B_实拍配文",    "table_id": "tblxxx", "skill": "pipeline-B"}
  },
  "states": {
    "draft": "草稿",
    "pending_review": "待审核",
    "pending_publish": "待发布",
    "published": "已发布",
    "archived": "回收"
  }
}
```

**9 张表在飞书里手建好 → 把 table_id 填进来**。

---

## 4. formulas/ 公式库

```json
// title_formulas.json
{
  "F1": {
    "id": "F1",
    "name": "对比反差型",
    "template": "{反共识观点} | {具体场景}",
    "example": "衣如云，自有气度 | 9 件香云纱撑起一整年",
    "weight": 0.8,
    "use_count": 0
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✓ | F1-F6 / B1-B3 / V1-V4 等唯一标识 |
| `name` | ✓ | 公式名（给 agent 看的） |
| `template` | ✓ | 模板字符串，agent 用作 LLM prompt |
| `example` | ✓ | 真实示例，1-2 个 |
| `weight` | × | 选公式时的偏好权重（默认 0.5） |
| `use_count` | × | 公式被使用次数（避让用，可省略） |

**最少 6 个 title + 3 个 body + 4 个 visual 才能跑 4 管线**。

---

## 5. lark_config.json — 飞书表映射(落库目标)

`pipelines/` 概念已弃(ADR-0003,旧配置已删除)。现在品牌只需 `lark_config.json` 声明**落库目标表**(飞书工位据此写,技能不碰 table_id):
- `base.app_token`(或 .env 的 `LARK_APP_TOKEN`)
- `review_tables` / `public_tables`:逻辑表名 → table_id(如 `account_teardown_library`=账号拆解库、`teardown_library`=爆款拆解库)。

取数不在品牌配置里 —— 由全局取数口(`.env` 的 `XHS_FETCH_CHAIN`)决定,与品牌无关。

---

## 6. 验证接入

```bash
# 1. 加载品牌（应输出 brand.slogan）
python3 -c "from skills.lib.brand_kb import load_brand; b = load_brand('新品牌ID'); print(b['profile']['slogan'])"

# 2. 4 管线各 setup 一次
for p in A1 A2 A3 B; do
  python3 skills/pipeline-$p/scripts/run_${p,,}.py setup --brand 新品牌ID --output $p.json
done

# 3. 注入 LLM + finalize（端到端）
python3 skills/pipeline-A1/scripts/run_a1.py finalize --brand 新品牌ID --notes-file notes.json

# 4. 飞书表里能看到 3 条新记录 + 封面图 attachment
```

---

## 7. 复制现成品牌最快

```bash
# 把观云的数据拷一份，改 brand_id + 飞书 ID 即可
cp -r brands/观云 brands/新品牌ID
# 改 profile.json 里的 brand_id / name / slogan
# 改 lark_config.json 里的 app_token + 9 张表 table_id
# 公式库按需替换
```

**最小改动**：profile.json + lark_config.json = 2 个文件就能跑（公式库和管线配置用观云的也能跑，只是风格不像新品牌）。
