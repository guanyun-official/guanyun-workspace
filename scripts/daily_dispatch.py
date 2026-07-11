"""轻调度器 CLI(#8):每天派活——列出/落地今天每号每模式该出的活(待出文案),**绝不自动发布**。

  python3 -m scripts.daily_dispatch           # 干跑:打印今天派活清单(不写库)
  python3 -m scripts.daily_dispatch --write    # 过红线闸把活落成『待出文案』占位(已在途去重)

红线:调度器只把活推到「待出文案」;出稿走 draft_one(→草稿待发),发布与 AI 声明永远人手。
"""
from __future__ import annotations

import argparse

from orchestrator import config, dispatch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="观云")
    ap.add_argument("--write", action="store_true", help="落库为『待出文案』占位(默认干跑只打印)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand}")
    rows = dispatch.dispatch(a.brand, write=a.write)
    print(f"今天派活 {len(rows)} 条(号×模式):")
    for r in rows:
        tag = r.get("skipped") or (f"→待出文案 {r.get('note_id')}" if a.write else "(干跑)")
        print(f"  {r['account']:20} {r['content_type']:12} 技能={r['gen_skill']:22} 素材={r['material_needs']}  {tag}")
        print(f"    素材来源[{r['sourcing']}]:{r['sourcing_hint']}")
    if not a.write:
        print("(干跑:未写库。加 --write 把活落成『待出文案』占位)")
    print("红线:调度器只派活到『待出文案』,绝不出稿即发、绝不代勾 AI 声明——出稿走 draft_one,发布/声明人手。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
