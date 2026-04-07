"""
PostgreSQL Row-Level Security (RLS) context helpers.

These utilities manage per-session tenant context variables that are read by
PostgreSQL RLS policies to enforce data isolation between organisations.

Typical usage
-------------
In the Django middleware that resolves the active organisation::

    from core.rls import set_rls_tenant, clear_rls_tenant

    # After resolving request.organization:
    set_rls_tenant(request.organization.id)

    # In process_response / process_exception:
    clear_rls_tenant()

For superadmin code paths that must cross tenant boundaries::

    from core.rls import bypass_rls

    with bypass_rls():
        Report.objects.all()  # sees rows across all tenants

Database compatibility
----------------------
All functions are **no-ops on non-PostgreSQL backends** (e.g. SQLite in local
development) so the same code works across environments without conditionals at
the call site.
"""

import logging
from contextlib import contextmanager
from typing import Any

from django.db import connection

logger = logging.getLogger(__name__)

_PG_VENDOR = "postgresql"

# The empty string is treated as "no tenant" by the RLS policies, which then
# deny access to all tenant-scoped rows (secure default).
_NO_TENANT = ""
_NO_USER = ""
_BYPASS_OFF = "off"
_BYPASS_ON = "on"


def _is_postgresql() -> bool:
    """Return ``True`` when the current default DB connection is PostgreSQL."""
    return connection.vendor == _PG_VENDOR


def _has_open_connection() -> bool:
    """Return ``True`` when the Django connection is already opened."""
    return getattr(connection, "connection", None) is not None


def _should_use_local(local: bool | None) -> bool:
    if local is not None:
        return local
    return bool(getattr(connection, "in_atomic_block", False))


def _set_rls_setting(name: str, value: str, *, local: bool | None = None) -> None:
    """Persist one RLS setting at session scope or transaction scope."""
    if not _is_postgresql():
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, %s)",
            [name, value, _should_use_local(local)],
        )


def _get_rls_setting(name: str, *, default: str = "") -> str:
    """Read the current RLS setting value, falling back to *default* when unset."""
    if not _is_postgresql():
        return default
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        row = cursor.fetchone()
    value = row[0] if row else None
    if value in (None, ""):
        return default
    return str(value)


def set_rls_tenant(org_id: Any, *, local: bool | None = None) -> None:
    """Set the active tenant context for RLS policies.

    Uses PostgreSQL's ``set_config`` to store the organisation primary key so
    that RLS policies can restrict rows to the current tenant.  The value
    is transaction-local inside ``transaction.atomic()`` blocks and otherwise
    persists for the lifetime of the underlying database connection until
    explicitly reset via :func:`clear_rls_tenant`.

    Args:
        org_id: Primary key of the active :class:`Organization` (UUID or int).
                Converted to ``str`` before being stored.
    """
    _set_rls_setting("app.current_org_id", str(org_id), local=local)


def clear_rls_tenant(*, local: bool | None = None) -> None:
    """Clear the active tenant context so RLS denies all tenant-scoped rows.

    Should be called at the end of every request (in middleware
    ``process_response`` and ``process_exception`` hooks) to ensure connections
    returned to a pool carry no leftover tenant state.
    """
    _set_rls_setting("app.current_org_id", _NO_TENANT, local=local)


def set_rls_user(user_id: Any, *, local: bool | None = None) -> None:
    """Set the active user context for policies that must remain user-scoped."""
    _set_rls_setting("app.current_user_id", str(user_id), local=local)


def clear_rls_user(*, local: bool | None = None) -> None:
    """Clear the active user context."""
    _set_rls_setting("app.current_user_id", _NO_USER, local=local)


def set_rls_bypass(enabled: bool = True, *, local: bool | None = None) -> None:
    """Enable or disable the RLS bypass flag.

    When ``enabled=True``, RLS policies allow all rows regardless of the active
    tenant.  This should only be used for controlled superadmin operations or
    during database migrations.

    Args:
        enabled: ``True`` to enable bypass; ``False`` to restore normal policy
                 enforcement.
    """
    value = _BYPASS_ON if enabled else _BYPASS_OFF
    _set_rls_setting("app.bypass_rls", value, local=local)


def reset_rls_context(*, local: bool | None = None, only_if_connection_open: bool = False) -> None:
    """Reset both tenant and bypass settings to the secure default state.

    ``only_if_connection_open`` avoids opening a brand-new PostgreSQL
    connection just to clear state during middleware cleanup for requests that
    never touched the database.
    """
    if not _is_postgresql():
        return
    if only_if_connection_open and not _has_open_connection():
        return
    clear_rls_tenant(local=local)
    clear_rls_user(local=local)
    set_rls_bypass(False, local=local)


@contextmanager
def bypass_rls():
    """Context manager that temporarily disables RLS enforcement.

    Intended for superadmin code paths that must access cross-tenant data.
    The bypass flag is cleared in the ``finally`` block even when the body
    raises an exception.

    On non-PostgreSQL backends this context manager is a no-op.

    Example::

        from core.rls import bypass_rls

        with bypass_rls():
            all_courses = Course.objects.all()  # sees rows from every tenant
    """
    if not _is_postgresql():
        yield
        return
    previous = _get_rls_setting("app.bypass_rls", default=_BYPASS_OFF)
    try:
        set_rls_bypass(True)
        yield
    finally:
        set_rls_bypass(previous == _BYPASS_ON)
