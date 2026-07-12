"""跑一天 CLI(人只管头尾的『中间一条龙』):一条命令产出"今天每号要发什么(草稿+素材,待人审)"。

  python3 -m scripts.run_day                    # 干跑:列今天要出的活(不写库)
  python3 -m scripts.run_day --write             # 落『草稿待发』(stub 占位,零成本验证接线)
  python3 -m scripts.run_day --write --llm real   # 出真文案(≈2元/条)落『草稿待发』,人打开 base 审

头(人)=按需/自主拍素材;尾(人)=在 base 点审/发/打勾。中间(本命令)= 排期→出文案→挂素材→草稿待发。
红线:**绝不自动发布、绝不代勾 AI 声明**——只推到『草稿待发』。
"""
from __future__ import annotations

import argparse

from orchestrator import config, dispatch, feishu_io


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="观云")
    ap.add_argument("--write", action="store_true", help="落库为『草稿待发』(默认干跑只列活)")
    ap.add_argument("--llm", choices=["stub", "real"], default="stub",
                    help="stub 零成本占位 / real 出真文案(≈2元/条)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand} llm={a.llm} write={a.write}")
    rows = dispatch.run_day(a.brand, llm_mode=a.llm, write=a.write)
    ok = [r for r in rows if r.get("status") == dispatch.NS.DRAFT_PENDING]
    bad = [r for r in rows if r.get("status", "").startswith("✗")]
    print(f"\n今天每号要发什么({len(rows)} 条活):")
    for r in rows:
        tail = (f"→草稿待发 {r.get('note_id')}  「{r.get('title', '')}」" if r.get("note_id")
                else (r.get("error") and f"✗ {r['error']}") or r.get("status", ""))
        print(f"  {r['account']:20} {r['content_type']:12} 技能={r['gen_skill']:22} 素材={r['material_needs']}  {tail}")
    if a.write:
        feishu_io.log_run(summary=f"跑一天 出稿{len(ok)}条 失败{len(bad)}({a.llm})", action="跑一天")
        print(f"\n✅ 落库 {len(ok)} 条『草稿待发』(失败 {len(bad)})。人打开飞书笔记表筛『草稿待发』即可审。")
        print("红线:止于草稿待发——发布与 AI 声明永远人手(见 asserting-ai-disclosure)。")
    else:
        print("\n(干跑:未写库。加 --write 落『草稿待发』;再加 --llm real 出真文案)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
