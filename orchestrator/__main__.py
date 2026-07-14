"""`python3 -m orchestrator <动词>` —— agent 的手伸出来的地方(Action Interface)。

以前这层叫 `scripts/`,里面住着三条导轨(tag_materials / daily_dispatch / draft_one)——
它们不是"入口",是**流程**:替 agent 决定了先干什么、怎么判、干几条。
拆完之后,**全景图里没有"脚本"这一层了**:只有 harness 的原子,和用它们的 agent。
"""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
