"""Pin a watch operation to one tenant without changing its caller's RLS context."""

from contextlib import contextmanager

from django.db import connection

from core.rls import set_rls_bypass, set_rls_tenant


@contextmanager
def watch_tenant(organization_id):
    """Must be inside an atomic block. SET LOCAL changes roll back with that block on failure."""
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_org_id',true),current_setting('app.bypass_rls',true)")
        old_tenant, old_bypass = cursor.fetchone()
    change_tenant = old_tenant != str(organization_id)
    change_bypass = old_bypass == "on"
    if change_tenant:
        set_rls_tenant(organization_id, local=True)
    if change_bypass:
        set_rls_bypass(False, local=True)
    try:
        yield
    finally:
        if not connection.needs_rollback:
            if change_tenant:
                set_rls_tenant(old_tenant or "", local=True)
            if change_bypass:
                set_rls_bypass(True, local=True)
