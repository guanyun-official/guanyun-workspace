"""
brand_kb.py — 「品牌库注入」seam(见 CONTEXT.md / ADR-0001)。

把 brands/<brand>/ 的静态品牌资产(定位/人设/调性/禁用词/公式)加载成可注入的上下文。
**纯能力技能不进库翻**——由编排/框架调本模块捞出品牌上下文,再注入给技能。
动态数据(待审/爆款情报/库存/审核状态)不在这里,在飞书(见 ADR-0002)。
不依赖 LLM。
"""
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_brand(brand_id: str) -> dict:
    """
    加载品牌完整档案（profile + formulas + principles + lark_config）。
    静态品牌资产，供框架注入给纯能力技能（见 ADR-0001）。
    """
    base = WORKSPACE / "brands" / brand_id
    if not base.exists():
        raise FileNotFoundError(f"品牌目录不存在: {base}")

    profile = _load_json(base / "profile.json")

    formulas = {
        "title": _load_json(base / "formulas" / "title_formulas.json")["formulas"],
        "body": _load_json(base / "formulas" / "body_formulas.json")["formulas"],
        "visual": _load_json(base / "formulas" / "visual_formulas.json")["formulas"],
    }
    principles = _load_json(base / "formulas" / "modification_principles.json")["principles"]

    lark_config = _load_json(base / "lark_config.json")

    return {
        "brand_id": brand_id,
        "profile": profile,
        "formulas": formulas,
        "principles": principles,
        "lark_config": lark_config,
        "formulas_dir": str(base / "formulas"),
        "explosive_dir": str(base / "knowledge_base" / "explosive"),
    }


def get_formula(formulas: dict, dim: str, fid: str) -> dict:
    """按 ID 取具体公式（title/body/visual）"""
    return next((f for f in formulas[dim] if f["id"] == fid), None)


def get_principle(principles: list, pid: str) -> dict:
    """按 ID 取具体原则"""
    return next((p for p in principles if p["id"] == pid), None)


def get_table_id(lark_config: dict, table: str) -> str:
    """取表 ID。待审表走 review_tables，其他走 public_tables"""
    rt = lark_config.get("review_tables", {})
    pub = lark_config.get("public_tables", {})
    if table in rt:
        return rt[table]["table_id"]
    if table in pub:
        return pub[table]["table_id"]
    raise KeyError(f"未知表: {table}")


def get_used_formulas(brand_id: str) -> set:
    """
    扫描所有已落地的 explosive JSON，提取历史用过的公式 ID。
    用于避让规则：本次生成的公式不应与历史重复。
    """
    explosive_dir = WORKSPACE / "brands" / brand_id / "knowledge_base" / "explosive"
    used = set()
    if not explosive_dir.exists():
        return used
    for f in sorted(explosive_dir.glob("target_explosive_*.json")):
        try:
            data = _load_json(f)
            for k in ("title_formula", "body_formula", "visual_formula"):
                if k in data:
                    used.add(data[k])
            for k in ("title_formulas", "body_formulas", "visual_formulas"):
                if k in data:
                    used.update(data[k])
        except Exception:
            pass
    return used


def get_auto_keywords(brand: dict) -> list:
    """品牌默认搜索关键词（A1/A2 不指定时用）。优先 profile.auto_keywords，
    否则从 products[].keywords 派生，再否则用 brand_name。全程不硬编码品牌词。"""
    p = brand["profile"]
    ak = p.get("auto_keywords")
    if ak:
        return ak if isinstance(ak, list) else [ak]
    derived = [k for prod in p.get("products", []) for k in prod.get("keywords", [])]
    return derived or [p.get("brand_name", "")]


def get_craft_pool(brand: dict) -> list:
    """可用工艺/面料词池：从 products[].keywords 去重派生（单一真相源，不硬编码）。"""
    seen, pool = set(), []
    for prod in brand["profile"].get("products", []):
        for k in prod.get("keywords", []):
            if k not in seen:
                seen.add(k); pool.append(k)
    return pool


def get_tag_pool(brand: dict) -> list:
    """标签词池：工艺词 + 调性词去重，供 tags prompt 用，不硬编码品牌词。"""
    pool = get_craft_pool(brand) + list(brand["profile"].get("tone_keywords", []))
    seen, out = set(), []
    for k in pool:
        if k not in seen:
            seen.add(k); out.append(k)
    return out


def select_formulas(brand: dict, n: int = 3, dim: str = "title") -> list:
    """
    自动选公式（带避让）。
    从 {dim} 公式库中选 n 个，避开已用过的。
    返回 [(formula_id, formula_dict), ...]
    """
    pool = brand["formulas"][dim]
    used = get_used_formulas(brand["brand_id"])
    available = [f for f in pool if f["id"] not in used]
    if len(available) < n:
        # 降级：接受复用
        available = list(pool)
    # 优先按 applicable_pipelines 含本管线选
    return available[:n]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    args = ap.parse_args()
    b = load_brand(args.brand)
    print(f"品牌: {b['profile']['brand_name']}")
    print(f"Slogan: {b['profile']['slogan']}")
    print(f"Title 公式: {len(b['formulas']['title'])} 条")
    print(f"Body 公式: {len(b['formulas']['body'])} 条")
    print(f"Visual 公式: {len(b['formulas']['visual'])} 条")
    print(f"修饰原则: {len(b['principles'])} 条")
    print(f"待审表: {list(b['lark_config'].get('review_tables', {}).keys())}")
    print(f"已用公式: {get_used_formulas(args.brand) or '无'}")
