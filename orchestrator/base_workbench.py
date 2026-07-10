"""BaseWorkbench: schema + live record 迁移计划的只读工作台。

第一版只读 `schema/test`，把目标 SourceOwnership 清单落成机器可读 dry-run。
它不写 Base；后续物理删字段/加字段必须从这里生成计划、备份、执行、dump schema。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from . import config


@dataclass(frozen=True)
class FieldRule:
    table: str
    field: str
    action: str
    reason: str
    field_type: str = "text"
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableRule:
    table: str
    action: str
    reason: str


TABLE_RULES: tuple[TableRule, ...] = (
    TableRule("笔记表", "keep", "Note 状态机唯一源"),
    TableRule("素材表", "keep", "Material 投影账本；大文件仍归素材盘"),
    TableRule("衣服总表", "keep", "SKU/Product catalog"),
    TableRule("账号表", "keep", "Account registry；不存方法论"),
    TableRule("内容类型表", "keep", "ContentType tag index；不存 playbook know-how"),
    TableRule("运行日志表", "keep", "Orchestrator run log"),
    TableRule("面料·工艺库", "keep", "结构化工艺/面料事实"),
    TableRule("灵感库", "keep", "外部灵感与选题入口"),
    TableRule("关键词库", "keep", "关键词/tag taxonomy"),
    TableRule("目标客户", "keep", "audience intelligence；不作为账号画像 owner"),
    TableRule("素人推广案例", "keep", "KOC/推广案例情报"),
    TableRule("Issue 表", "rename", "改语义为员工需求/运营问题反馈；开发 issue 只进 GitHub"),
    TableRule("修订日志", "keep", "内容修订日志；需补关联笔记"),
    TableRule("技能表", "delete_table", "skill owner 是 git repo + skills.lock.json；测试 Base 不保留技能双源"),
)


FIELD_RULES: tuple[FieldRule, ...] = (
    # 笔记表
    FieldRule("笔记表", "账号", "add", "显式 link 到账号表，替代 lookup 作为 Note 所属账号事实", "link"),
    FieldRule("笔记表", "数据用途", "add", "区分真实运营/演练/压测，替代仅靠 _SIM/_UAT/_STRESS 前缀", "select", ("真实运营", "演练", "压测")),
    FieldRule("笔记表", "运行批次", "add", "贯穿 Note/RunLog/fixture 清理的 run_id", "text"),
    FieldRule("笔记表", "发布包路径", "add", "指向盘上待发布包", "text"),
    FieldRule("笔记表", "token花费(元)", "delete_field", "成本 owner 是运行日志表.成本_元；Note 不保存第二成本源"),
    FieldRule("笔记表", "人工时(小时)", "delete_field", "结算/工时不属于 Note 状态机"),
    FieldRule("笔记表", "结算日期", "delete_field", "结算日期不属于 Note 状态机"),
    FieldRule("笔记表", "颜色", "delete_field", "颜色事实应来自衣服或素材 metadata"),
    FieldRule("笔记表", "账号(自动)", "delete_field", "账号 owner 已迁到显式 账号 link；删除旧 lookup"),

    # 素材表
    FieldRule("素材表", "相对路径", "add", "明确盘上素材路径，避免链接字段混用 URL/路径", "text"),
    FieldRule("素材表", "素材哈希", "add", "支持搬家、去重、幂等登记", "text"),
    FieldRule("素材表", "数据用途", "add", "区分真实运营/演练/压测", "select", ("真实运营", "演练", "压测")),
    FieldRule("素材表", "验收状态", "add", "AI 生成素材必须先验收再可用于 Note", "select", ("待验收", "可用", "弃用")),
    FieldRule("素材表", "文件", "delete_field", "Base 不当大媒体库；素材文件 owner 是素材盘"),
    FieldRule("素材表", "颜色", "delete_field", "颜色事实应来自衣服或素材 metadata"),

    # 衣服总表
    FieldRule("衣服总表", "内容优先级", "add", "给 planner/员工排序 SKU", "select", ("高", "中", "低")),
    FieldRule("衣服总表", "生命周期状态", "add", "SKU 状态显性化", "select", ("待拍", "可发", "暂停", "归档")),
    FieldRule("衣服总表", "素材缺口摘要", "add", "planner 可重算投影，不人工维护", "text"),
    FieldRule("衣服总表", "排期表-关联衣服", "deprecate_field", "旧命名；目标是笔记表-关联衣服"),

    # 账号表
    FieldRule("账号表", "workspace_ref", "add", "指向 workspace account owner 文件", "text"),
    FieldRule("账号表", "画像状态", "add", "员工可见 account-teardown 状态", "select", ("占位", "已拆解", "需重跑")),
    FieldRule("账号表", "画像更新时间", "add", "account-teardown 最近更新时间", "datetime"),
    FieldRule("账号表", "自动排产", "add", "员工界面开关；需与 workspace launched/cadence 明确优先级", "select", ("开启", "暂停", "跟随workspace")),
    FieldRule("账号表", "受众", "delete_field", "受众理解 owner 是 workspace 账号画像，Base 不保留第二真相源"),

    # 内容类型表
    FieldRule("内容类型表", "slug", "add", "稳定 key，避免中文改名断历史", "text"),
    FieldRule("内容类型表", "启用状态", "add", "员工筛选 tag 是否启用", "select", ("启用", "停用")),
    FieldRule("内容类型表", "展示顺序", "add", "员工界面排序", "number"),
    FieldRule("内容类型表", "workspace_playbook_ref", "add", "只读指针，指向 workspace playbook owner", "text"),
    FieldRule("内容类型表", "取数字段·切面", "delete_field", "playbook know-how owner 是 workspace.playbooks"),
    FieldRule("内容类型表", "文案元模版", "delete_field", "playbook know-how owner 是 workspace.playbooks"),

    # 运行日志表
    FieldRule("运行日志表", "run_id", "add", "贯穿 automation/daily/heartbeat/fixture 清理", "text"),
    FieldRule("运行日志表", "automation_id", "add", "标记触发来源", "text"),
    FieldRule("运行日志表", "duration_ms", "add", "运行耗时", "number"),
    FieldRule("运行日志表", "error_type", "add", "错误分类便于告警聚合", "text"),
    FieldRule("运行日志表", "数据用途", "add", "区分真实运营/演练/压测", "select", ("真实运营", "演练", "压测")),

    # 面料·工艺库
    FieldRule("面料·工艺库", "事实来源", "add", "工艺事实出处", "text"),
    FieldRule("面料·工艺库", "可信级别", "add", "事实可信度", "select", ("高", "中", "低")),
    FieldRule("面料·工艺库", "禁用说法", "add", "避免工艺误述", "text"),
    FieldRule("面料·工艺库", "排期表-关联面料·工艺", "deprecate_field", "旧命名；目标是笔记表-关联面料·工艺"),

    # 灵感库
    FieldRule("灵感库", "来源平台", "add", "情报来源", "select", ("小红书", "抖音", "其他")),
    FieldRule("灵感库", "来源账号", "add", "外部账号", "text"),
    FieldRule("灵感库", "采集时间", "add", "情报采集时间", "datetime"),
    FieldRule("灵感库", "可借鉴点", "add", "生成可读的结构化洞察", "text"),
    FieldRule("灵感库", "禁用片段/搬运风险", "add", "防 source leak", "text"),
    FieldRule("灵感库", "去重键", "add", "幂等采集", "text"),

    # 关键词库
    FieldRule("关键词库", "启用状态", "add", "关键词是否进入运营", "select", ("启用", "停用")),
    FieldRule("关键词库", "禁用原因", "add", "停用原因", "text"),
    FieldRule("关键词库", "平台", "add", "适用平台", "select", ("小红书", "全平台")),

    # 目标客户
    FieldRule("目标客户", "人群假设", "add", "受众假设，不作为账号画像 owner", "text"),
    FieldRule("目标客户", "证据链接", "add", "受众证据", "text"),
    FieldRule("目标客户", "更新时间", "add", "情报更新时间", "datetime"),
    FieldRule("目标客户", "适用账号", "add", "关联账号", "link"),

    # 素人推广案例
    FieldRule("素人推广案例", "合作状态", "add", "增长合作状态", "select", ("候选", "联系中", "合作中", "已结束", "弃用")),
    FieldRule("素人推广案例", "转化指标", "add", "效果摘要", "text"),
    FieldRule("素人推广案例", "适用账号", "add", "关联账号", "link"),
    FieldRule("素人推广案例", "素材授权状态", "add", "素材使用授权", "select", ("未知", "已授权", "未授权")),

    # Issue 表 / 修订日志 / 技能表
    FieldRule("Issue 表", "github_issue_url", "add", "需要开发跟踪时回填 GitHub Issue 链接", "text"),
    FieldRule("Issue 表", "归属域", "add", "员工需求分域", "select", ("内容", "素材", "账号", "员工界面", "开发")),
    FieldRule("Issue 表", "关联技能", "delete_field", "skill owner 是 git，不在员工需求表维护"),
    FieldRule("修订日志", "关联笔记", "add", "修订必须能回到 Note", "link"),
    FieldRule("修订日志", "修订类型", "add", "修订分类", "select", ("文案", "事实", "素材", "合规", "其他")),
    FieldRule("修订日志", "审核人", "add", "人审责任人", "text"),
    FieldRule("修订日志", "关联技能", "delete_field", "skill owner 是 git，不在修订日志维护"),
)

SIMPLE_CREATE_TYPES = frozenset({"text", "select", "number", "datetime"})
LINK_TARGET_TABLES = {
    ("笔记表", "账号"): "账号表",
    ("目标客户", "适用账号"): "账号表",
    ("素人推广案例", "适用账号"): "账号表",
    ("修订日志", "关联笔记"): "笔记表",
}


def _load_schema_dir(schema_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(schema_dir.glob("*.json")):
        if p.name == "_tables.json":
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        out[data["table_name"]] = data
    return out


def _fields(schema: dict) -> set[str]:
    return {f["field_name"] for f in schema.get("fields", [])}


def build_plan(schema_dir: Path | None = None) -> dict:
    """Build a dry-run migration plan from local schema files. No network, no writes."""
    schema_dir = schema_dir or (config.WORKSPACE / "schema" / "test")
    schemas = _load_schema_dir(schema_dir)
    table_rules = {r.table: r for r in TABLE_RULES}
    field_rules = list(FIELD_RULES)

    tables = []
    for table, schema in sorted(schemas.items()):
        rule = table_rules.get(table, TableRule(table, "unknown", "schema 中存在但目标清单未声明"))
        existing = _fields(schema)
        fields = []
        for fr in sorted((r for r in field_rules if r.table == table), key=lambda x: (x.action, x.field)):
            exists = fr.field in existing
            if fr.action == "add" and exists:
                status = "already_present"
            elif fr.action == "add":
                status = "missing"
            elif fr.action in {"delete_field", "deprecate_field"} and exists:
                status = "present"
            else:
                status = "already_absent"
            fields.append({**asdict(fr), "exists": exists, "status": status})
        tables.append({
            "table": table,
            "table_action": rule.action,
            "reason": rule.reason,
            "fields": fields,
        })

    required_tables = {name for name, rule in table_rules.items() if rule.action != "delete_table"}
    missing_tables = sorted(required_tables - set(schemas))
    unknown_tables = sorted(set(schemas) - set(table_rules))
    summary = {
        "tables_total": len(schemas),
        "missing_target_tables": missing_tables,
        "unknown_tables": unknown_tables,
        "add_missing": sum(1 for t in tables for f in t["fields"] if f["action"] == "add" and f["status"] == "missing"),
        "delete_present": sum(1 for t in tables for f in t["fields"] if f["action"] == "delete_field" and f["status"] == "present"),
        "deprecate_present": sum(1 for t in tables for f in t["fields"] if f["action"] == "deprecate_field" and f["status"] == "present"),
        "deprecate_tables": sorted(r.table for r in table_rules.values() if r.action == "deprecate_table" and r.table in schemas),
        "delete_tables": sorted(r.table for r in table_rules.values() if r.action == "delete_table" and r.table in schemas),
        "rename_tables": sorted(r.table for r in table_rules.values() if r.action == "rename" and r.table in schemas),
    }
    return {"schema_dir": str(schema_dir), "summary": summary, "tables": tables}


def has_blocking_drift(plan: dict) -> bool:
    """Dry-run 自身的硬失败：目标清单与 schema 表集合不一致。字段缺失不是失败，是迁移计划。"""
    s = plan["summary"]
    return bool(s["missing_target_tables"] or s["unknown_tables"])


def simple_create_body(field: dict) -> dict:
    """Translate a dry-run add field into Bitable field-create JSON.

    Link/lookup/formula/attachment 这类需要额外 property 或数据迁移的字段不在第一刀自动建。
    """
    field_type = field["field_type"]
    if field_type not in SIMPLE_CREATE_TYPES:
        raise ValueError(f"{field['table']}.{field['field']} is not a simple field: {field_type}")
    body = {"name": field["field"], "type": field_type}
    options = field.get("options") or ()
    if field_type == "select" and options:
        body["property"] = {"options": [{"name": x} for x in options]}
    return body


def simple_adds(plan: dict) -> list[dict]:
    """Missing add fields safe for first-wave physical creation."""
    out = []
    for table in plan["tables"]:
        for field in table["fields"]:
            if field["action"] == "add" and field["status"] == "missing" and field["field_type"] in SIMPLE_CREATE_TYPES:
                out.append(field)
    return out


def link_target_table(field: dict) -> str:
    key = (field["table"], field["field"])
    try:
        return LINK_TARGET_TABLES[key]
    except KeyError as exc:
        raise ValueError(f"{field['table']}.{field['field']} has no link target table") from exc


def link_create_body(field: dict, table_ids: dict[str, str]) -> dict:
    """Translate an approved missing link field into Bitable DuplexLink create JSON."""
    if field["field_type"] != "link":
        raise ValueError(f"{field['table']}.{field['field']} is not a link field: {field['field_type']}")
    target = link_target_table(field)
    return {
        "name": field["field"],
        "type": "link",
        "property": {
            "table_id": table_ids[target],
            "multiple": True,
            "back_field_name": f"{field['table']}-{field['field']}",
        },
    }


def link_adds(plan: dict) -> list[dict]:
    """Missing link fields safe for second-wave physical creation."""
    out = []
    for table in plan["tables"]:
        for field in table["fields"]:
            if (
                field["action"] == "add"
                and field["status"] == "missing"
                and field["field_type"] == "link"
                and (field["table"], field["field"]) in LINK_TARGET_TABLES
            ):
                out.append(field)
    return out


def present_deletes(plan: dict) -> list[dict]:
    """Present fields whose target action is physical deletion."""
    out = []
    for table in plan["tables"]:
        for field in table["fields"]:
            if field["action"] == "delete_field" and field["status"] == "present":
                out.append(field)
    return out
