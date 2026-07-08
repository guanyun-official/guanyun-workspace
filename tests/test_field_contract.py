"""字段契约锁:代码消费的字段常量 ⊆ 测试 Base schema 声明(代码消费 ⊆ 声明)。

why:52 处中文字段名 magic string 是最脆的一环——飞书 UI 里有人把「文案草稿」改成
「正文草稿」,代码里 NF.DRAFT 还指旧名,引擎写回静默落空、发布包拼不出文案,而单测全绿。
本测试把「代码认识的字段」钉死在「schema 声明的字段」上:任一字段常量在 schema 里找不到,
立刻红灯——UI 改名再也藏不住。纯读本地 schema 契约,零网络。

它与 schema_diff.py(测试库现况 vs 基线 dump)互补:那个盯 UI→schema 漂移,
这个盯 schema→代码 消费缺口。两道合起来 = 字段名端到端不失联。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrator import bitable, engine


def _schema_field_names(table_name: str) -> set[str]:
    d = json.loads((ROOT / "schema" / "test" / f"{table_name}.json").read_text(encoding="utf-8"))
    return {f["field_name"] for f in d["fields"]}


def _schema_select_options(table_name: str, field_name: str) -> set[str]:
    d = json.loads((ROOT / "schema" / "test" / f"{table_name}.json").read_text(encoding="utf-8"))
    for f in d["fields"]:
        if f["field_name"] == field_name:
            return set(f.get("options") or [])
    return set()


def _schema_field_types(table_name: str) -> dict:
    d = json.loads((ROOT / "schema" / "test" / f"{table_name}.json").read_text(encoding="utf-8"))
    return {f["field_name"]: f["type"] for f in d["fields"]}


class TestFieldConstantContract(unittest.TestCase):
    # 每个字段词汇类都声明自己 TABLE,测试自动遍历——将来新增词汇类只需加进这里
    FIELDSETS = [bitable.NoteFields, bitable.MaterialFields,
                 bitable.RunLogFields, bitable.ContentTypeFields]

    def test_declared_constants_subset_of_schema(self):
        for fs in self.FIELDSETS:
            declared = bitable.declared_field_names(fs)
            self.assertTrue(declared, f"{fs.__name__} 未声明任何字段常量(TABLE 元属性被误当字段?)")
            self.assertTrue(getattr(fs, "TABLE", ""), f"{fs.__name__} 缺 TABLE 声明,无法定位 schema")
            schema = _schema_field_names(fs.TABLE)
            missing = sorted(f for f in declared if f not in schema)
            self.assertEqual(
                missing, [],
                f"{fs.__name__}({fs.TABLE}) 这些字段常量在 schema 里已不存在(UI 改名/删字段?):{missing}")

    def test_table_json_exists_for_each_fieldset(self):
        for fs in self.FIELDSETS:
            p = ROOT / "schema" / "test" / f"{fs.TABLE}.json"
            self.assertTrue(p.exists(), f"{fs.__name__}.TABLE={fs.TABLE} 无对应 schema/test/{fs.TABLE}.json")


class TestStatusValueContract(unittest.TestCase):
    """状态取值契约:引擎写回/路由用的 NoteStatus 取值 ⊆ 状态列 select 枚举。

    why:写回一个 select 没声明的值(如 UI 把「待发布」改成「排队中」),飞书会拒写或静默,
    引擎自以为推进了状态、笔记却卡死在原地,而单测全绿。锁死枚举 → 改选项即红灯。"""

    def test_note_status_values_subset_of_select_options(self):
        opts = _schema_select_options(bitable.NoteStatus.TABLE, bitable.NoteStatus.FIELD)
        self.assertTrue(opts, f"{bitable.NoteStatus.FIELD} 字段在 schema 里没有 select options?")
        values = bitable.declared_field_names(bitable.NoteStatus)
        illegal = sorted(v for v in values if v not in opts)
        self.assertEqual(
            illegal, [],
            f"NoteStatus 这些取值不在「{bitable.NoteStatus.FIELD}」select 枚举(UI 改/删选项?):{illegal}")


# 类型契约:这些字段的 schema 类型是代码的硬假设。(字段常量, 所属表, 期望类型, 漂了会怎样)
_NF, _RLF = bitable.NoteFields, bitable.RunLogFields
TYPE_CONTRACT = [
    (_NF.STATUS, _NF.TABLE, "select", "NoteStatus 枚举锁与状态写回都依赖 select 类型"),
    (_NF.AI_DECLARED, _NF.TABLE, "checkbox", "guard.assert_ai_declared 靠真值判断——类型漂了 AI 声明红线门失灵"),
    (_NF.PUBLISHED_AT, _NF.TABLE, "datetime", "parse_ts 依赖毫秒时间戳——漂了回流窗口/控量判断出错"),
    (_NF.PLANNED_AT, _NF.TABLE, "datetime", "parse_ts 依赖毫秒时间戳——漂了催审入场计时出错"),
    (_NF.LINKED_MATERIALS, _NF.TABLE, "link", "link_record_ids 靠 link 结构——漂了发布包配套素材清单丢失"),
    (_RLF.TIME, _RLF.TABLE, "datetime", "_monthly_cost_cny 按本月过滤日志——漂了成本核算/预算熔断失灵"),
]


class TestFieldTypeContract(unittest.TestCase):
    """类型契约锁:名字对但类型漂(datetime→text 等)是名字锁的盲区——代码会静默错:
    parse_ts 取不到日期、checkbox 真值门失灵、link 解析空。把类型关键字段的 schema 类型也钉死,
    与名字锁、取值锁合成三层契约。纯读本地 schema,零网络。"""

    def test_type_critical_fields_keep_their_type(self):
        for field, table, want, why in TYPE_CONTRACT:
            types = _schema_field_types(table)
            self.assertEqual(
                types.get(field), want,
                f"{table}.{field} 类型漂移:schema={types.get(field)!r} 期望={want!r}——{why}")


class TestCostFieldMigrationGuard(unittest.TestCase):
    """M3 迁移守卫:成本_元 数值字段一旦在测试库运行日志表建好,engine.COST_FIELD 必须与
    schema 里的实际字段名严格一致,并登记进 RunLogFields。否则 _cost_of_log 会永远静默走
    detail 回退——正是契约锁要防的静默漂移。字段还没建时本测试自动跳过(不误报)。

    这道守卫是自激活的:字段一出现,断言立即生效,逼开发者把 COST_FIELD 对齐 schema
    并补进常量层;不用记得在迁移后手动加测试。"""

    def test_cost_field_aligned_once_migrated(self):
        runlog = _schema_field_names(bitable.RunLogFields.TABLE)
        cost_like = sorted(f for f in runlog if "成本" in f or "花费" in f)
        if not cost_like:
            self.skipTest("成本_元 数值字段尚未迁移到测试库运行日志表(issue#10 M3);字段建好后本测试自动生效")
        self.assertIn(
            engine.COST_FIELD, runlog,
            f"运行日志表已有成本类字段 {cost_like},但 engine.COST_FIELD={engine.COST_FIELD!r} 不在其中"
            f"——_cost_of_log 会永远走 detail 回退(静默漂移),请把 COST_FIELD 对齐 schema 实际字段名")
        self.assertIn(
            engine.COST_FIELD, bitable.declared_field_names(bitable.RunLogFields),
            f"{engine.COST_FIELD!r} 已建但未登记进 RunLogFields——请补常量,让契约锁覆盖它")


if __name__ == "__main__":
    unittest.main()
