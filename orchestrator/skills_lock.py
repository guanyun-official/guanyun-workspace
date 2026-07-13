"""skills.lock.json 的结构语义(单一真相源:check_p1 与单测共用,防校验与实现漂移)。

两类 source:
  远程 source —— 来自 git 仓库,须含 repo + 40 位真 commit sha,可追溯安装版本。
  本地 source —— workspace 原生(如 content-loop),无 repo;以 sha=='local' 显式标记。
共同键:name/local/ref/sha/skills/install,且 skills 非空。

validate() 纯结构语义(不碰文件系统),故单测可零环境依赖;
local 路径存在性属部署校验,留在 check_p1.sh 脚本层。
"""
from __future__ import annotations

import re

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_COMMON_KEYS = ("name", "local", "ref", "sha", "skills", "install")


def is_local_source(s: dict) -> bool:
    """本地(workspace 原生)source 的显式标记:sha 记 'local'(远程 source 是 40 位真 commit)。"""
    return s.get("sha") == "local"


def shadowed_skills(local_names, installed_resolve) -> list[str]:
    """**双源遮蔽哨兵**(dogfood 2026-07-14 用户戳出"技能到底在哪?不是要唯一真源吗"后加的)。

    归一前:巧荷特化技能一半住 workspace 的 `local-skills/`(writing-* / tagging-material),
    一半住技能仓(qiaohe-amateur-miner / qiaohe-video-script / video-editing…)——同类资产两个家。
    而 `load_gen_skill` 查找顺序是 `local-skills/` → `skills/`(**local 优先**):技能仓一旦出现同名技能,
    workspace 那份会**静默盖住**它(跑的技能 ≠ 锁记录/装进来的那份),而 `installed_drift` 只比
    "远程仓 HEAD vs lock sha",这种同名遮蔽一个字都不报。双源漂移的入口就在这。

    **已根治**(2026-07-14):4 个技能收编进 qiaohe-skill,`local-skills/` 整个删除,
    `load_gen_skill` 只查 `skills/` 一个路径 → 遮蔽从物理上不可能发生。
    本函数留作**回归哨兵**:谁要是把 `local-skills/` 加回来、又和 skills/ 里的同名技能是两份真身,当场报。
    正常态下 local_names 为空([]),返回 []。

    判据:某名字同时在 local-skills/ 有目录,且 `skills/<name>` 解析到的真身**不在 local-skills 底下**
    → 两份不同真身抢一个名字 → 报。
    installed_resolve(name) -> 真身绝对路径(str)或 None(没装)。纯逻辑,文件系统 IO 由调用方注入(可零环境单测)。
    """
    errs: list[str] = []
    for name in sorted(local_names or []):
        target = installed_resolve(name)
        if not target:
            continue                                   # 没装进 skills/ → 只有 local 一份,单源,没事
        if "/local-skills/" in str(target).replace("\\", "/"):
            continue                                   # symlink 指回 local-skills 自己 → 同一份文件,单源
        errs.append(f"技能「{name}」双源遮蔽:local-skills/ 和 skills/(→{target})是两份不同真身,"
                    "load_gen_skill 只查 skills/,local-skills 那份是死的却在误导人。"
                    "技能唯一真源=qiaohe-skill 仓,删掉 local-skills/。")
    return errs


def installed_drift(lock: dict, head_of) -> list[str]:
    """锁版 vs 安装现场实际 HEAD 比对(治『锁版形同虚设』:源仓库被 pull 后 symlink 悄悄变、锁没跟上,
    跑到的技能≠锁记录的版本却无人察觉)。head_of(local_path)->实际HEAD sha 或 None。
    None(路径缺失/非 git)跳过不误报——存在性属部署校验(check_p1)。纯逻辑,git IO 由调用方注入(可零环境单测)。
    只查远程 source(本地 source sha='local' 无 commit 概念)。返回漂移列表(空=对齐)。"""
    errs: list[str] = []
    for s in lock.get("sources") or []:
        if is_local_source(s):
            continue
        actual = head_of(s.get("local", ""))
        if actual is None:
            continue  # 取不到实际 HEAD(路径不在/非 git)→部署校验层管,这里不误报
        locked = str(s.get("sha", ""))
        if actual != locked:
            errs.append(f"技能源 {s.get('name', '?')} 锁版漂移:lock={locked[:8]} 实际HEAD={str(actual)[:8]}"
                        "(源仓库变了没重装,或锁改了没重跑 install)")
    return errs


def validate(lock: dict) -> list[str]:
    """返回问题列表(空=合法)。远程 source 须有 repo+真 sha;本地 source 免 repo。"""
    errs: list[str] = []
    srcs = lock.get("sources")
    if not isinstance(srcs, list) or not srcs:
        return ["sources 为空或非列表"]
    for s in srcs:
        name = s.get("name", "?")
        for k in _COMMON_KEYS:
            if k not in s:
                errs.append(f"source {name} 缺键 {k}")
        if not s.get("skills"):
            errs.append(f"source {name} skills 为空")
        if is_local_source(s):
            continue  # 本地 source:workspace 原生,不要求 repo
        if "repo" not in s:
            errs.append(f"远程 source {name} 缺键 repo(本地 source 须以 sha='local' 标记)")
        elif not _SHA40.match(str(s.get("sha", ""))):
            errs.append(f"远程 source {name} 的 sha 非 40 位 commit: {s.get('sha')}")
    return errs
