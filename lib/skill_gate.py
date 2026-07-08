"""
skill_gate.py — 技能校验闸引擎(架构评审候选 A)。

窄接口、深内核:各技能只**声明** required + 一组 checks,不再各自重写"读字段/遍历/汇总报告"的骨架。
check = 一个 `(payload) -> [错误字符串]` 的可调用;run() 跑完汇总成 (ok, errors)。
内置常用 check:required / no_source_leak(防搬运) / banned_words / each_has。新增规则 = 加一个 check 函数。
"""
from __future__ import annotations

import re


# ---------- 文本工具 ----------
def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "", flags=re.UNICODE)


def _char_ngrams(s: str, n: int) -> set:
    s = _norm(s)
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else set()


def has_text(s: str) -> bool:
    return bool(_norm(s))


def walk_strings(obj, path: str = "", skip: tuple = ()):
    """递归 yield (path, 字符串值);skip 里的(任意层)字段名跳过。"""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip:
                continue
            yield from walk_strings(v, f"{path}.{k}" if path else k, skip)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]", skip)


# ---------- 可组合 checks:每个返回 (payload) -> [error] ----------
def required(fields: list):
    """必填齐全(空字符串/空数组/空对象都算缺)。"""
    def chk(p):
        miss = [f for f in fields if f not in p or p.get(f) in ("", [], {}, None)]
        return [f"缺必填字段: {miss}"] if miss else []
    return chk


def no_source_leak(source_text: str, n: int = 10, skip: tuple = ()):
    """防搬运:payload 任何字符串都不得含 source_text 的 ≥n 连续字符片段。"""
    grams = _char_ngrams(source_text, n)
    def chk(p):
        if not grams:
            return []
        errs = []
        for path, val in walk_strings(p, skip=skip):
            hit = _char_ngrams(val, n) & grams
            if hit:
                sample = sorted(hit, key=len, reverse=True)[0]
                errs.append(f"疑似搬运 @ {path}: 含原文片段「…{sample}…」(≥{n}字),请抽象化/占位符化")
        return errs
    return chk


def banned_words(words, skip: tuple = ()):
    """禁用词:payload(去 skip 字段)文本里不得出现 words。"""
    wset = {w for w in (words or []) if w}
    def chk(p):
        text = "".join(v for _, v in walk_strings(p, skip=skip))
        hit = sorted(w for w in wset if w in text)
        return [f"命中禁用词: {hit}"] if hit else []
    return chk


def each_has(field: str, subkeys: list):
    """list 字段非空,且每项都带 subkeys(如 brand_points 每条带 item/point/source)。"""
    def chk(p):
        items = p.get(field)
        if not items:
            return [f"{field} 为空(必须有)"]
        errs = []
        for i, item in enumerate(items):
            if not (isinstance(item, dict) and all(item.get(k) for k in subkeys)):
                errs.append(f"{field}[{i}] 缺 {subkeys}")
        return errs
    return chk


# ---------- 引擎 ----------
def run(payload: dict, checks: list):
    """跑所有 check,汇总。返回 (ok: bool, errors: list[str])。"""
    errors = []
    for c in checks:
        errors.extend(c(payload))
    return (not errors), errors
