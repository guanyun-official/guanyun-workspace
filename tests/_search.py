"""测试助手:过滤型 search_records / get_record mock。

反 mock 假绿:之前 mock 忽略 conditions 返全量,search 条件拼错(字段名/operator/conjunction)照样绿。
这里的 search_mock **按 conditions 真过滤 fixture** → 条件拼错就漏/多命中 → 测试红,真正测住条件正确性。
"""
from orchestrator import bitable


def search_mock(fake):
    """过滤型 feishu_io.search_records mock。fake={table_name:[records]}。按 conditions(is 操作符)真过滤。"""
    def _search(table, conditions=None, conjunction="and", page_size=100):
        rows = fake.get(table, [])
        if not conditions:
            return list(rows)

        def match(r):
            oks = []
            for c in conditions:
                fv = bitable.text(r["fields"].get(c["field_name"])).strip()
                vals = [str(v) for v in c.get("value", [])]
                oks.append(fv in vals if c["operator"] == "is" else True)
            return all(oks) if conjunction == "and" else any(oks)
        return [r for r in rows if match(r)]
    return _search


def get_record_mock(fake):
    """feishu_io.get_record mock:按 record_id 从 fake 各表找,找不到→None。"""
    def _get(table, rid):
        for r in fake.get(table, []):
            if r["record_id"] == rid:
                return r
        return None
    return _get
