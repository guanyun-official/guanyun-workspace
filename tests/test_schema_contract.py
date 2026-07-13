"""schema 读侧漂告警(ADR-0009 P1):代码消费的每个字段名/枚举值 ⊆ 上次 dump 的活 schema(schema/test/)。

飞书 UI 改字段名 / 删或改 select 选项而代码词汇(bitable.*Fields / *Status)没跟上 → 这里红,
不留到运行时静默落空(list_records 读到 None、写库静默失败、过滤条件永不命中)。
离线纯读快照,零网络。快照刷新:python3 scripts/dump_schema.py --base test。

真事故(本契约抓出):KeywordFields.DISABLED 曾写 '禁用',但活 schema『启用状态』枚举是 启用/停用
→ load_keywords 的『≠禁用』永远为真,停用词从不被筛掉。'禁用' 既非字段名也非选项 → 漂移红。
"""
import json
import unittest
from pathlib import Path

from orchestrator import bitable as B

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "test"

# 词汇类 → 表名。字段名类(*Fields)与枚举值类(*Status/AutoSched/*Source)一起查:
# 每个声明的中文串都必须是该表的『活字段名』或『活 select 选项』之一(union 覆盖混装了值常量的 KeywordFields)。
VOCAB_TABLE = [
    (B.NoteFields, "笔记表"), (B.MaterialFields, "素材表"), (B.AccountFields, "账号表"),
    (B.RunLogFields, "运行日志表"), (B.ContentTypeFields, "内容类型表"),
    (B.InspirationFields, "灵感库"), (B.KeywordFields, "关键词库"),
    (B.NoteStatus, "笔记表"), (B.AutoSched, "账号表"),
    (B.MaterialStatus, "素材表"), (B.MaterialSource, "素材表"),
]


def _live(table: str):
    """活 schema 快照里该表的字段名集合 + 所有 select 选项集合。"""
    fields = json.loads((SCHEMA / f"{table}.json").read_text(encoding="utf-8"))["fields"]
    names = {f["field_name"] for f in fields}
    opts = {o for f in fields for o in (f.get("options") or [])}
    return names, opts


class TestSchemaContract(unittest.TestCase):
    def test_declared_vocab_subset_of_live_schema(self):
        drift: dict[str, list[str]] = {}
        for cls, table in VOCAB_TABLE:
            names, opts = _live(table)
            miss = set(B.declared_field_names(cls)) - names - opts
            if miss:
                drift[f"{cls.__name__}→{table}"] = sorted(miss)
        self.assertEqual(
            drift, {},
            f"字段/枚举漂移(代码词汇不在活 schema——飞书改了名/删了选项,或代码写错):{drift}。"
            "确认后:改代码对齐,或 python3 scripts/dump_schema.py --base test 刷新快照。",
        )

    def test_snapshot_present(self):
        # 快照缺失=契约形同虚设(空集∩→误绿),显式要求每张被消费的表都有快照
        for _, table in VOCAB_TABLE:
            self.assertTrue((SCHEMA / f"{table}.json").exists(), f"缺 schema 快照: {table}(先跑 dump_schema)")

    def test_live_probe_uses_same_vocab_list(self):
        # 单一真相:离线契约(本文件)与活探针(check_schema_drift)必须查同一张词汇→表映射,
        # 否则一处漏了某表/类,另一处却以为覆盖了(反"两份清单各自漂")。
        from scripts.check_schema_drift import VOCAB_TABLE as LIVE
        norm = lambda vt: sorted((cls.__name__, table) for cls, table in vt)
        self.assertEqual(norm(VOCAB_TABLE), norm(LIVE),
                         "离线契约与活探针的词汇→表清单不一致,同步二者(单一真相)")


if __name__ == "__main__":
    unittest.main()
