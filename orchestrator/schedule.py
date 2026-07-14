"""作息表:**能设定时器的手**(Tools)+ **能看见自己日程的眼**(Observation)。

★这是整轮拆导轨里最容易搞错的一块,把话说死★

    | | 归谁 |
    |---|---|
    | **"能读能写定时器"这个能力** | **Harness 的一只手** ← 就是本文件 |
    | **"几点醒 / 醒来干什么 / 要不要改自己的作息"** | **Agent 的判断** ← 一个字都不在这里 |

2026-07-14 卸掉的那 5 条 cron **不是心跳,是我替数字生命排的作息表**:
    0 8  * * *  daily_dispatch --write      ← 我决定了"每天 8 点派活"
    0 19 * * 0  collect_metrics             ← 我决定了"周日采回流"
    30 23 * * * backup_tables               ← 我决定了"每天备份"
定时器一响就跑一个写死的流程,**agent 完全不在场**。

现在:**定时器触发后唯一该做的事是「叫醒 agent」** —— 它醒来自己看板、自己判断、自己动手。
人只需要说一句「每天早上看看有没有活」,**它自己算出该几点、自己写进 crontab、自己跑一次验证**。
运营哪天在飞书说「周报改成周五发」,它自己去改 —— 不用发版,不用找我。

—— harness 只保证两件事:**它有那只手**(读写 crontab)、**它有那双眼**(看得见自己现在的日程)。

## 这只手唯一的红线(不是判断,是保护世界)

**只碰自己写的行。** 每行带 `# gy-agent:<名字>` 标记;没有这个标记的行(用户自己的 cron、
系统的 cron)**一个字都不许动**。crontab 是用户机器上的公共设施,不是 agent 的私产。
"""
from __future__ import annotations

import re
import subprocess

MARK = "# gy-agent"          # 我们的行的标记;没这个标记的行绝不碰
_LINE = re.compile(rf"^(?P<cron>[^#]+?)\s+(?P<cmd>.+?)\s+{re.escape(MARK)}:(?P<name>[^\s:]+)"
                   rf"(?::(?P<why>.*))?$")


class ScheduleError(RuntimeError):
    """作息表读写失败(crontab 不可用等)。message 面向人可读。"""


def _read_raw() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        if "no crontab" in (r.stderr or "").lower():
            return []                       # 还没有 crontab = 空日程,不是错
        raise ScheduleError(f"读 crontab 失败:{(r.stderr or '').strip()[:200]}")
    return r.stdout.splitlines()


def _write_raw(lines: list[str]) -> None:
    body = "\n".join(lines).rstrip() + "\n"
    r = subprocess.run(["crontab", "-"], input=body, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise ScheduleError(f"写 crontab 失败:{(r.stderr or '').strip()[:200]}")


def list_all() -> dict:
    """**我现在的作息表是什么**(Observation)。

    分两堆,而且必须分清 —— 这是那条红线的另一半:
      · `我的`   —— 带 gy-agent 标记的,**我能改**
      · `别人的` —— 用户/系统自己的 cron 行,**我一个字都不碰**(只报数,连内容都不该乱读乱改)
    """
    mine, others = [], []
    for ln in _read_raw():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = _LINE.match(s)
        if m:
            mine.append({"名字": m.group("name"), "何时": m.group("cron").strip(),
                         "干什么": m.group("cmd").strip(), "为什么": (m.group("why") or "").strip()})
        else:
            others.append(s)
    return {"我的": mine, "别人的(不碰)": len(others)}


def dry_run(do: str) -> dict:
    """**在 cron 那样的干净环境里,真跑一次这条命令,把真实输出摆给你看。**

    ★为什么必须有这只眼(2026-07-14 数字生命第三天挖到的最深一口井)★

    老板说「以后每天早上帮我看看有没有活」。它去试那条"叫醒自己"的命令:

        $ env -i HOME=... PATH=... claude -p "..."
        Not logged in · Please run /login
        [exit=0]                                   ← ★★★ 失败,却报成功 ★★★

    **登录态活不过 cron,而且退出码是 0。** 如果它就这么把班装进 crontab:
      · 它会出现在 `schedule` 里
      · 它会出现在你的 crontab 里,写着「每天早上看看有没有活」,**人一读就懂**
      · 它每天早上准时**空转一次,什么都没发生,然后报告成功**

    —— 一条**人看得懂、你会信、而它根本不干活**的假班。**空壳比没有更危险:
    没有,你知道没有;空壳,你以为有。**

    它按「要么真做出来,要么删掉,别留着骗人」**拒绝了装这条班**。这是对的。

    所以 harness 欠它的不是一条规则,是**一双眼**:装班之前,**替它把这条命令在
    cron 那样的干净环境里真跑一次**,把 stdout / stderr / 退出码原样交出来。

    ⚠️ **这里不判断"它醒没醒"** —— 退出码 0 也可能是空壳(上面就是活证据)。
    **看输出、判断这条命令到底醒没醒,是 agent 的事。** harness 只负责把真相摆出来。
    """
    import os
    env = {"HOME": os.environ.get("HOME", ""),          # cron 的环境 ≈ 空:只有 HOME/PATH/SHELL
           "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
           "SHELL": "/bin/sh"}
    try:
        r = subprocess.run(["/bin/sh", "-c", do], capture_output=True, text=True,
                           env=env, timeout=90)
    except subprocess.TimeoutExpired:
        return {"退出码": None, "stdout": "", "stderr": "(90 秒没跑完,超时)",
                "环境": "cron 那样的干净环境(只有 HOME/PATH/SHELL)"}
    return {
        "退出码": r.returncode,
        "stdout": (r.stdout or "")[-800:],
        "stderr": (r.stderr or "")[-800:],
        "环境": "cron 那样的干净环境(只有 HOME/PATH/SHELL —— 你交互 shell 里的登录态/环境变量都不在)",
        "⚠️": "**退出码 0 不等于它醒了。** 真栽过:`claude -p` 在这个环境里回 "
              "『Not logged in』**而退出码是 0**。**看输出,自己判断它到底醒没醒。**",
    }


def set_job(name: str, when: str, do: str, why: str, verified: bool = False) -> dict:
    """给自己排一个班(或改掉同名的那个)。**几点、干什么、为什么 —— 全是你(agent)决定的。**

    · name —— 这个班叫什么(同名 = 覆盖,幂等)
    · when —— 五段 cron 表达式,如 `0 8 * * *`。**是你算出来的**,harness 不替你想
    · do   —— 到点跑什么命令。**唯一该做的事是「叫醒你自己」**,不是跑一个写死的流程
    · why  —— **一句人话:为什么是这个点、这是给谁排的班**。
              必填 —— 运营/老板打开 crontab 得看得懂你在干嘛。一张没人看得懂的作息表 = 黑箱。
    · verified —— **你已经用 `dry_run` 真跑过这条命令、并亲眼确认它能叫醒你**。

    ★为什么要你先验★ 一条装得进 crontab、人读得懂、却每天空转的假班,
    **比没有更危险**(没有,你知道没有;空壳,你以为有)。
    这不是替你判断 —— `dry_run` 把真实输出摆给你,**醒没醒你自己看**;
    这里只要求你**确实看过**。
    """
    if not (name and when and do and why):
        raise ScheduleError("排班要四样都有:名字 / 何时(cron)/ 干什么(命令)/ **为什么(人话)**。"
                            "『为什么』不许省 —— 人得看得懂你给自己排了什么班。")
    if len(when.split()) != 5:
        raise ScheduleError(f"cron 表达式要五段(分 时 日 月 周),你给的是「{when}」")
    if not verified:
        raise ScheduleError(
            "先验一下这条命令**在 cron 那样的环境里到底能不能叫醒你**:\n"
            f"    python3 -m orchestrator schedule.dry-run --do {do!r}\n"
            "它会把真实的 stdout/stderr/退出码摆给你看。**看完你自己判断醒没醒**,"
            "确认了再加 `--verified` 装班。\n"
            "⚠️ **退出码 0 不等于它醒了** —— 真栽过:`claude -p` 在干净环境里回『Not logged in』"
            "**而退出码是 0**。装一条每天空转、却写着「每天早上看看有没有活」的假班,"
            "**比不装更危险**。")
    lines = [ln for ln in _read_raw()
             if not (m := _LINE.match(ln.strip())) or m.group("name") != name]   # 同名先摘掉(幂等)
    lines.append(f"{when} {do} {MARK}:{name}:{why}")
    _write_raw(lines)
    return {"排好了": name, "何时": when, "干什么": do, "为什么": why,
            "自证": "python3 -m orchestrator schedule  → 看它真的在表里"}


def remove(name: str) -> dict:
    """撤掉自己的一个班。**只撤带 gy-agent 标记且同名的那行**,别人的 cron 一个字都不动。"""
    before = _read_raw()
    after = [ln for ln in before
             if not (m := _LINE.match(ln.strip())) or m.group("name") != name]
    if len(after) == len(before):
        return {"没找到": name, "提示": "看看 `schedule` 里有哪些班(只列带 gy-agent 标记的)"}
    _write_raw(after)
    return {"撤掉了": name}
