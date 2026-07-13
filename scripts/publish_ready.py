"""发布就绪 CLI:对『已批准』笔记,按素材来源自动判 AI 声明要不要勾,并(可选)推进『待发布』。

  python3 -m scripts.publish_ready            # 只报告:每条已批准 该不该勾 AI声明
  python3 -m scripts.publish_ready --write     # 把『可发』的推进『待发布』(全实拍免勾/已勾)

红线:**绝不自动发布**(只到待发布,发是人手)、**绝不代勾 AI声明**(实拍免除、含AI要求你勾)。
"""
from __future__ import annotations

import argparse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/publish_ready.py 也能跑(不止 -m)

from orchestrator import config, feishu_io, publish


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--write", action="store_true", help="把『可发』的推进『待发布』(默认只报告)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand} write={a.write}")
    rows = publish.review_approved(a.brand, write=a.write)
    if not rows:
        print("（当前没有『已批准』待处理的笔记）")
        return 0
    print(f"\n已批准 {len(rows)} 条,AI声明自动判定:")
    for r in rows:
        adv = "  →已推进待发布" if r["advanced"] else ""
        print(f"  {r['verdict']:26} 素材含AI={r['ai_required']} 已勾={r['declared']} 「{r['title']}」{adv}")
        for m in r.get("materials", []):                         # 待发布用哪张:编号+来源+可开链接
            seg = f" · {m['note']}" if m.get("note") else ""
            print(f"      取素材 {m['code']}({m['type']}/{m['source']}){seg}  → {m['取用链接'] or '(无链接)'}")
    if a.write:
        n = sum(1 for r in rows if r["advanced"])
        feishu_io.log_run(summary=f"发布就绪 推进{n}条待发布(AI声明自动判定)", action="发布就绪")
        print(f"\n✅ 推进 {n} 条→待发布(人手发布+打勾即完成)。含AI未勾的留在已批准,请先勾AI声明。")
    else:
        print("\n(只报告。加 --write 把『可发』的推进待发布)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
