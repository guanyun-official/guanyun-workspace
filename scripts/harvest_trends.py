"""找热点→灵感库 CLI:把 skill/agent 找到的热点灵感落灵感库(去重),供 trend_imitate 承接出稿。

  python3 -m scripts.harvest_trends --file trends.json          # 干跑预览(不写)
  python3 -m scripts.harvest_trends --file trends.json --write   # 落灵感库

trends.json = [{"标题": "...", "可借鉴": "...", "源链接": "https://..."}]
(『找』由 explosive-teardown / miner 技能或 agent 产出这个 JSON;本命令只管『落』+去重。)
落库后 daily_dispatch 会把未转化灵感列成『爆款模仿待办』,draft_one --title-seed 承接。
"""
from __future__ import annotations

import argparse
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/harvest_trends.py 也能跑(不止 -m)

from orchestrator import config, feishu_io, trends


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--file", required=True, help="热点灵感 JSON(list of {标题,可借鉴,源链接})")
    ap.add_argument("--write", action="store_true", help="落灵感库(默认干跑预览)")
    a = ap.parse_args()
    items = json.loads(open(a.file, encoding="utf-8").read())
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand} 输入{len(items)}条 write={a.write}")
    res = trends.harvest_trends(items, a.brand, write=a.write)
    print(f"\n新增 {len(res['新增'])} 条{'(已落灵感库)' if a.write else '(干跑预览)'}:")
    for t in res["新增"]:
        print(f"  + {t}")
    if res["去重跳过"]:
        print(f"去重跳过 {len(res['去重跳过'])} 条(标题已在库)")
    # 没正文的灵感:**不再是红线空洞,但仍是信息缺失**(2026-07-14 真跑校正)。
    # 小红书详情页对非登录**只吐 452 字节空壳**(真抓验证过)→ 正文在无凭证时根本抓不到。
    # 而正文**本来就不进 prompt**(compose_prompt 不收它)→ LLM 没见过 → 逐字搬它物理上不可能。
    # 防搬运门现在守的是 **LLM 真正看得见的东西**:灵感标题 + 技能 few-shot 真实帖。
    # 所以无正文 ≠ 不能出稿;它只是少了一层"万一将来把正文喂进 prompt"的保护。如实说,别吓唬人。
    if res.get("无正文"):
        print(f"\nℹ️ {len(res['无正文'])} 条灵感没有原帖正文(非登录抓不到,小红书详情页只吐空壳)。")
        print("   不影响出稿:正文本来就不进 prompt,LLM 没见过 → 搬不了。")
        print("   防搬运门守的是 LLM 真看得见的:**灵感标题 + 技能 few-shot 真实帖**(逐字搬即拒)。")
        print("   有凭证(TIKHUB_API_KEY / 小红书 cookie)时可补正文,多一层保护。")
    if a.write and res["新增"]:
        feishu_io.log_run(summary=f"找热点落灵感库 {len(res['新增'])} 条", action="找热点", table="灵感库")
        print("\n下一步:daily_dispatch 会列成『爆款模仿待办』,draft_one --title-seed 承接出稿。")
    elif not a.write:
        print("\n(干跑:未写库。加 --write 落灵感库)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
