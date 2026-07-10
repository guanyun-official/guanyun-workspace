import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import base_workbench  # noqa: E402


def _write_table(root: Path, name: str, fields: list[tuple[str, str]]) -> None:
    (root / f"{name}.json").write_text(
        json.dumps({
            "table_name": name,
            "fields": [{"field_name": f, "type": t} for f, t in fields],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


class TestBaseWorkbench(unittest.TestCase):
    def setUp(self):
        self.schema = Path(tempfile.mkdtemp())
        for table in {r.table for r in base_workbench.TABLE_RULES}:
            _write_table(self.schema, table, [("占位", "text")])
        _write_table(self.schema, "内容类型表", [
            ("内容类型名", "text"),
            ("格式", "select"),
            ("所属账号", "link"),
            ("取数字段·切面", "text"),
            ("文案元模版", "text"),
        ])
        _write_table(self.schema, "笔记表", [
            ("排期编号", "text"),
            ("状态", "select"),
            ("账号(自动)", "lookup"),
            ("token花费(元)", "number"),
        ])
        _write_table(self.schema, "技能表", [("技能名称", "text")])

    def _field(self, plan: dict, table: str, field: str) -> dict:
        for t in plan["tables"]:
            if t["table"] == table:
                for f in t["fields"]:
                    if f["field"] == field:
                        return f
        self.fail(f"{table}.{field} not found")

    def test_build_plan_marks_content_type_knowhow_for_delete(self):
        plan = base_workbench.build_plan(self.schema)
        self.assertFalse(base_workbench.has_blocking_drift(plan))
        self.assertEqual(self._field(plan, "内容类型表", "取数字段·切面")["action"], "delete_field")
        self.assertEqual(self._field(plan, "内容类型表", "取数字段·切面")["status"], "present")
        self.assertEqual(self._field(plan, "内容类型表", "文案元模版")["status"], "present")

    def test_build_plan_marks_new_fixture_fields_missing(self):
        plan = base_workbench.build_plan(self.schema)
        use = self._field(plan, "笔记表", "数据用途")
        run = self._field(plan, "笔记表", "运行批次")
        self.assertEqual(use["action"], "add")
        self.assertEqual(use["status"], "missing")
        self.assertEqual(tuple(use["options"]), ("真实运营", "演练", "压测"))
        self.assertEqual(run["status"], "missing")

    def test_skill_table_is_deprecated_not_owner(self):
        plan = base_workbench.build_plan(self.schema)
        skill = next(t for t in plan["tables"] if t["table"] == "技能表")
        self.assertEqual(skill["table_action"], "deprecate_table")
        self.assertIn("skills.lock.json", skill["reason"])
        self.assertIn("技能表", plan["summary"]["deprecate_tables"])

    def test_simple_adds_and_create_body(self):
        plan = base_workbench.build_plan(self.schema)
        adds = {(f["table"], f["field"]): f for f in base_workbench.simple_adds(plan)}
        self.assertIn(("笔记表", "数据用途"), adds)
        body = base_workbench.simple_create_body(adds[("笔记表", "数据用途")])
        self.assertEqual(body["name"], "数据用途")
        self.assertEqual(body["type"], "select")
        self.assertEqual(
            [x["name"] for x in body["property"]["options"]],
            ["真实运营", "演练", "压测"],
        )

    def test_present_deletes(self):
        plan = base_workbench.build_plan(self.schema)
        deletes = {(f["table"], f["field"]) for f in base_workbench.present_deletes(plan)}
        self.assertEqual(
            deletes,
            {("内容类型表", "取数字段·切面"), ("内容类型表", "文案元模版")},
        )

    def test_unknown_or_missing_tables_are_blocking_drift(self):
        _write_table(self.schema, "陌生表", [("x", "text")])
        (self.schema / "技能表.json").unlink()
        plan = base_workbench.build_plan(self.schema)
        self.assertTrue(base_workbench.has_blocking_drift(plan))
        self.assertIn("陌生表", plan["summary"]["unknown_tables"])
        self.assertIn("技能表", plan["summary"]["missing_target_tables"])


if __name__ == "__main__":
    unittest.main()
