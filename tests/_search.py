"""测试助手:过滤型 search_records / get_record mock。

反 mock 假绿:之前 mock 忽略 conditions 返全量,search 条件拼错(字段名/operator/conjunction)照样绿。
这里的 search_mock **按 conditions 真过滤 fixture** → 条件拼错就漏/多命中 → 测试红,真正测住条件正确性。
"""
from orchestrator import bitable


def search_mock(fake):
    """过滤型 feishu_io.search_records mock。fake={table_name:[records]}。
    按 conditions 真过滤——支持 is / isEmpty / isNotEmpty / isGreater(日期窗,value=["ExactDate",ms] 或 [ms]),
    覆盖冷热分离查询(状态=已发 AND 链接isEmpty、AND 实际发布日 isGreater)。未知算子放行(不误红)。"""
    def _search(table, conditions=None, conjunction="and", page_size=100):
        rows = fake.get(table, [])
        if not conditions:
            return list(rows)

        def _one(c, r):
            op = c["operator"]
            raw = r["fields"].get(c["field_name"])
            fv = bitable.text(raw).strip()
            if op == "is":
                return fv in [str(v) for v in c.get("value", [])]
            if op == "isEmpty":
                return fv == ""
            if op == "isNotEmpty":
                return fv != ""
            if op == "isGreater":                       # 日期窗:field 时间 > 阈值 ms
                ts = bitable.parse_ts(raw)
                thr = next((int(v) for v in c.get("value", []) if str(v).isdigit()), None)
                return bool(ts and thr is not None and ts.timestamp() * 1000 > thr)
            return True                                 # 未知算子:放行(不误红)
        return [r for r in rows
                if (all if conjunction == "and" else any)(_one(c, r) for c in conditions)]
    return _search


def get_record_mock(fake):
    """feishu_io.get_record mock:按 record_id 从 fake 各表找,找不到→None。"""
    def _get(table, rid):
        for r in fake.get(table, []):
            if r["record_id"] == rid:
                return r
        return None
    return _get
