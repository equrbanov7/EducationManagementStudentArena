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


def _is_postgresql() -> bool:
    """Return ``True`` when the current default DB connection is PostgreSQL."""
    return connection.vendor == _PG_VENDOR


def set_rls_tenant(org_id: Any) -> None:
    """Set the active tenant context for RLS policies (session-level).

    Uses PostgreSQL's ``set_config`` to store the organisation primary key so
    that RLS policies can restrict rows to the current tenant.  The value
    persists for the lifetime of the underlying database connection and must be
    explicitly reset via :func:`clear_rls_tenant` at the end of each request
    to avoid state leaking between requests on pooled connections.

    Args:
        org_id: Primary key of the active :class:`Organization` (UUID or int).
                Converted to ``str`` before being stored.
    """
    if not _is_postgresql():
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org_id', %s, false)",
            [str(org_id)],
        )


def clear_rls_tenant() -> None:
    """Clear the active tenant context so RLS denies all tenant-scoped rows.

    Should be called at the end of every request (in middleware
    ``process_response`` and ``process_exception`` hooks) to ensure connections
    returned to a pool carry no leftover tenant state.
    """
    if not _is_postgresql():
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org_id', %s, false)",
            [_NO_TENANT],
        )


def set_rls_bypass(enabled: bool = True) -> None:
    """Enable or disable the RLS bypass flag (session-level).

    When ``enabled=True``, RLS policies allow all rows regardless of the active
    tenant.  This should only be used for controlled superadmin operations or
    during database migrations.

    Args:
        enabled: ``True`` to enable bypass; ``False`` to restore normal policy
                 enforcement.
    """
    if not _is_postgresql():
        return
    value = "on" if enabled else "off"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.bypass_rls', %s, false)",
            [value],
        )


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
    try:
        set_rls_bypass(True)
        yield
    finally:
        set_rls_bypass(False)
