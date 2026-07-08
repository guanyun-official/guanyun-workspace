"""
skill_io.py — 技能脚本统一 I/O 契约(架构评审候选 C)。

约定:输入 = 文件路径 或 '-'(stdin)的 JSON;输出 = `{ok, ...}` JSON,成功 exit 0、失败 exit 1。
所有 skills/*/scripts 的脚本共用这一份,LLM 学一次契约、新技能直接复用。这是约定,不是框架。
"""
import json
import sys
from pathlib import Path
from typing import NoReturn


def load_json(arg, *, name="输入"):
    """读 JSON:arg 是文件路径,或 '-' 读 stdin。"""
    if arg in (None, ""):
        raise ValueError(f"缺{name}")
    text = sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")
    return json.loads(text)


def read_text(arg):
    """读纯文本:文件路径或 '-'(stdin);空参数返回 ''。"""
    if not arg:
        return ""
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")


def emit(ok, **fields) -> NoReturn:
    """打印 {ok, ...} 并按 ok 退出(失败 exit 1)。技能脚本的统一出口(总是退出,不返回)。"""
    print(json.dumps({"ok": ok, **fields}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)
