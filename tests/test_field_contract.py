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

from orchestrator import bitable


def _schema_field_names(table_name: str) -> set[str]:
    d = json.loads((ROOT / "schema" / "test" / f"{table_name}.json").read_text(encoding="utf-8"))
    return {f["field_name"] for f in d["fields"]}


def _schema_select_options(table_name: str, field_name: str) -> set[str]:
    d = json.loads((ROOT / "schema" / "test" / f"{table_name}.json").read_text(encoding="utf-8"))
    for f in d["fields"]:
        if f["field_name"] == field_name:
            return set(f.get("options") or [])
    return set()


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


if __name__ == "__main__":
    unittest.main()
