"""AccountKernel: Base 账号行 ↔ workspace Account data 的唯一源审计模块。

Base 负责员工界面、运行状态、平台外键；workspace 负责可版本化 know-how：
账号画像、strategy、playbooks、生成配方。这个 module 把两边收进一个窄
interface，检查的核心不是“同步两份数据”，而是阻止双真相源。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from . import accounts, bitable, feishu_io
from .bitable import AccountFields as AF
from .bitable import ContentTypeFields as CTF

DEPRECATED_CONTENT_TYPE_KNOWHOW_FIELDS = ("取数字段·切面", "文案元模版")


@dataclass(frozen=True)
class BaseAccount:
    record_id: str
    name: str
    xhs_id: str
    homepage: str
    audience: str
    launch_status: str
    content_type_names: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceAccount:
    name: str
    mode: str
    launched: bool
    content_types: tuple[str, ...]
    playbooks: tuple[str, ...]
    explicit_playbooks: bool
    profile_placeholder: bool
    error: str | None = None


@dataclass(frozen=True)
class BaseContentType:
    record_id: str
    name: str
    fmt: str
    account_ids: tuple[str, ...]
    deprecated_knowhow_fields: tuple[str, ...]


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def _tuple_texts(value) -> tuple[str, ...]:
    text = bitable.text(value)
    return tuple(x.strip() for x in text.split(",") if x.strip())


def base_accounts(records: list[dict]) -> list[BaseAccount]:
    out: list[BaseAccount] = []
    for raw in records:
        r = bitable.Record(raw)
        name = r.text(AF.NAME).strip()
        if not name:
            continue
        out.append(BaseAccount(
            record_id=r.record_id,
            name=name,
            xhs_id=r.text(AF.XHS_ID).strip(),
            homepage=r.text(AF.HOMEPAGE).strip(),
            audience=r.text(AF.AUDIENCE).strip(),
            launch_status=r.text(AF.LAUNCH_STATUS).strip(),
            content_type_names=_tuple_texts(r.raw(AF.CONTENT_TYPES_LOOKUP)),
        ))
    return out


def workspace_accounts(brand: str = "观云") -> list[WorkspaceAccount]:
    out: list[WorkspaceAccount] = []
    for name, acc in accounts.load_all(brand).items():
        strategy = acc.strategy or {}
        pbs = accounts.playbooks_of(strategy)
        content_types = tuple(dict.fromkeys(
            [str(x) for x in strategy.get("content_types", [])]
            + [str(pb.get("content_type") or pb.get("id")) for pb in pbs if pb.get("content_type") or pb.get("id")]
        ))
        out.append(WorkspaceAccount(
            name=name,
            mode=str(strategy.get("mode") or ""),
            launched=strategy.get("launched") is not False,
            content_types=content_types,
            playbooks=tuple(str(pb.get("id") or "") for pb in pbs if pb.get("id")),
            explicit_playbooks=bool(strategy.get("playbooks")),
            profile_placeholder="待 account-teardown" in acc.profile_text,
            error=acc.error,
        ))
    return out


def base_content_types(records: list[dict]) -> list[BaseContentType]:
    out: list[BaseContentType] = []
    for raw in records:
        r = bitable.Record(raw)
        name = r.text(CTF.NAME).strip()
        if not name:
            continue
        out.append(BaseContentType(
            record_id=r.record_id,
            name=name,
            fmt=r.text(CTF.FORMAT).strip(),
            account_ids=tuple(r.link_ids(CTF.ACCOUNT_LINK)),
            deprecated_knowhow_fields=tuple(
                field for field in DEPRECATED_CONTENT_TYPE_KNOWHOW_FIELDS
                if r.text(field).strip()
            ),
        ))
    return out


def build_checks(base: list[BaseAccount], workspace: list[WorkspaceAccount], ctypes: list[BaseContentType]) -> list[Check]:
    checks: list[Check] = []
    base_names = {a.name for a in base}
    workspace_names = {a.name for a in workspace}
    ctypes_names = {c.name for c in ctypes}
    active_workspace_types = {
        ctype for acc in workspace if acc.launched for ctype in acc.content_types
    }
    inactive_workspace_types = {
        ctype for acc in workspace if not acc.launched for ctype in acc.content_types
    }

    missing_workspace = sorted(base_names - workspace_names)
    missing_base = sorted(workspace_names - base_names)
    checks.append(Check(
        "account_identity",
        "PASS" if not missing_workspace and not missing_base else "FAIL",
        f"base_only={missing_workspace or '[]'} workspace_only={missing_base or '[]'}",
    ))

    bad_frontmatter = sorted(a.name for a in workspace if a.error)
    checks.append(Check(
        "workspace_frontmatter",
        "PASS" if not bad_frontmatter else "FAIL",
        f"bad={bad_frontmatter or '[]'}",
    ))

    placeholders = sorted(a.name for a in workspace if a.profile_placeholder)
    checks.append(Check(
        "account_profiles",
        "PASS" if not placeholders else "WARN",
        f"placeholder_profiles={placeholders or '[]'}",
    ))

    missing_active_types = sorted(active_workspace_types - ctypes_names)
    missing_inactive_types = sorted(inactive_workspace_types - ctypes_names)
    checks.append(Check(
        "content_types_declared",
        "PASS" if not missing_active_types else "FAIL",
        f"active_missing={missing_active_types or '[]'} inactive_missing={missing_inactive_types or '[]'}",
    ))

    unlinked_types = sorted(c.name for c in ctypes if not c.account_ids)
    checks.append(Check(
        "content_type_account_links",
        "PASS" if not unlinked_types else "WARN",
        f"unlinked={unlinked_types or '[]'}",
    ))

    base_owned_knowhow = sorted(c.name for c in ctypes if c.deprecated_knowhow_fields)
    checks.append(Check(
        "source_owner_content_type_knowhow",
        "PASS" if not base_owned_knowhow else "FAIL",
        f"base_owned_knowhow={base_owned_knowhow or '[]'} owner=workspace.playbooks",
    ))

    implicit_pb_accounts = sorted(a.name for a in workspace if a.launched and not a.explicit_playbooks)
    checks.append(Check(
        "source_owner_playbooks",
        "PASS" if not implicit_pb_accounts else "FAIL",
        f"implicit_playbooks={implicit_pb_accounts or '[]'} owner=workspace.playbooks",
    ))

    nameless = 4 - len(base) if len(base) < 4 else 0
    checks.append(Check(
        "base_account_rows",
        "PASS" if len(base) == 4 and not nameless else "FAIL",
        f"named_accounts={len(base)}",
    ))
    return checks


def build_audit(
    *,
    brand: str = "观云",
    list_records: Callable[[str], list[dict]] = feishu_io.list_records,
) -> dict:
    base = base_accounts(list_records(AF.TABLE))
    workspace = workspace_accounts(brand)
    ctypes = base_content_types(list_records(CTF.TABLE))
    checks = build_checks(base, workspace, ctypes)
    return {
        "brand": brand,
        "checks": [asdict(c) for c in checks],
        "base_accounts": [asdict(a) for a in base],
        "workspace_accounts": [asdict(a) for a in workspace],
        "content_types": [asdict(c) for c in ctypes],
    }


def has_failures(audit: dict) -> bool:
    return any(c["status"] == "FAIL" for c in audit["checks"])
