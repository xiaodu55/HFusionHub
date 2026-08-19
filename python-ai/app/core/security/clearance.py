"""Subject-level clearance context for document visibility ACL.

主体级 ACL 的 Python 侧核心：请求主体（subject）携带一个 clearance（密级）
等级，文档/向量分块携带一个 visibility（可见性）等级，检索时按
``rank(visibility) <= rank(clearance)`` 过滤——低权限主体永远看不到高于其
clearance 的内容（fail-closed）。

等级模型（按敏感度升序，两侧共用同一张表）：

- clearance: ``general`` < ``admin``（admin 拥有全部 clearance）
- visibility: ``general`` < ``confidential``（V85 迁移 DEFAULT 'general'）

传输方式与租户边界一致（``X-Tenant-Id`` 中间件 → contextvar）：Java 后端是
唯一的鉴权权威，经内部 token 边界向本服务传播 ``X-User-Clearance``；缺省按
最低权限 ``general`` 处理，非法值直接拒绝（与租户中间件同策略）。
"""

from __future__ import annotations

import contextvars
from typing import Any

# 按敏感度升序；下标即 rank，越靠后越敏感。
VISIBILITY_LEVELS: tuple[str, ...] = ("general", "confidential")
CLEARANCE_LEVELS: tuple[str, ...] = ("general", "admin")

DEFAULT_CLEARANCE = "general"
# metadata 缺失 visibility 的存量分块按 DB 缺省等级处理（V85 DEFAULT 'general'），
# 与 Java 侧 document.visibility 的默认值保持同一语义。
DEFAULT_VISIBILITY = "general"

_clearance_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "subject_clearance", default=None
)


def normalize_clearance(value: Any) -> str:
    """归一化 clearance；未知值 fail-closed 归入最低权限。"""
    if not value:
        return DEFAULT_CLEARANCE
    normalized = str(value).strip().lower()
    return normalized if normalized in CLEARANCE_LEVELS else DEFAULT_CLEARANCE


def normalize_visibility(value: Any) -> str:
    """归一化 visibility；未知/缺失值按最敏感侧的缺省语义处理。

    存量分块（V85 之前索引）没有 visibility 字段，按 DB 缺省 ``general``
    处理；显式传入的未知值不在此处吞掉——由调用方决定是否拒绝。
    """
    if not value:
        return DEFAULT_VISIBILITY
    return str(value).strip().lower()


def set_clearance(value: str | None) -> None:
    """设置当前请求主体的 clearance（中间件/请求入口调用）。"""
    _clearance_var.set(normalize_clearance(value))


def get_clearance() -> str:
    """返回当前主体 clearance；未设置时按最低权限 general（fail-closed）。"""
    return normalize_clearance(_clearance_var.get())


def clear_clearance() -> None:
    """清空 clearance 上下文（请求结束时调用，防止跨请求泄漏）。"""
    _clearance_var.set(None)


def allowed_visibilities(clearance: str | None = None) -> frozenset[str]:
    """给定 clearance 可见的 visibility 集合。"""
    rank = CLEARANCE_LEVELS.index(normalize_clearance(clearance))
    return frozenset(VISIBILITY_LEVELS[: rank + 1])


def build_acl_metadata_filter(clearance: str | None = None) -> dict[str, Any] | None:
    """构造检索用的 ACL metadata 过滤器。

    - admin（全 clearance）：返回 ``None``（不过滤，但也不是越权——全部可见）；
    - 其他主体：返回 ``{"visibility": [可见集合]}``，由存储层后过滤执行。
    """
    clearance = normalize_clearance(clearance)
    if clearance == CLEARANCE_LEVELS[-1]:
        return None
    return {"visibility": sorted(allowed_visibilities(clearance))}


def subject_can_see_metadata(metadata: Any) -> bool:
    """判断单条分块的 metadata 对当前主体是否可见（直读路径的 ACL 闸门）。

    与检索后过滤同一语义：``rank(visibility) <= rank(clearance)``，
    metadata 缺失 visibility 按 DB 缺省 ``general`` 处理；JSON 字符串形态
    （co-store 落盘格式）自行解析；未知 visibility 值 fail-closed 按最敏感
    等级处理（仅 admin 可见）。分块直读工具/端点必须先过此闸门再返回内容，
    否则确定性 chunk_id 可被枚举绕过检索层过滤。
    """
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    visibility = normalize_visibility(metadata.get("visibility"))
    if visibility not in VISIBILITY_LEVELS:
        visibility = VISIBILITY_LEVELS[-1]
    return visibility in allowed_visibilities(get_clearance())
