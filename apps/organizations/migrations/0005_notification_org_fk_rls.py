"""Move the InAppNotification RLS policy onto a real organization FK (FAZA 4).

Background
----------
``0004_expand_rls_scope`` enforced tenant isolation on
``notifications_inappnotification`` by reading the organisation id out of the
``metadata`` JSONB blob:

    recipient_id = current_user
    AND (metadata->>'organization_id' IS NULL
         OR metadata->>'organization_id' = current_org)

That rule is FAIL-OPEN: any future notification whose creator simply forgot to
put ``organization_id`` into ``metadata`` would have a NULL value there and be
visible to every tenant the recipient belongs to.

Fix
---
``notifications.0003`` added a real, indexed ``organization_id`` column and
backfilled it from the metadata. This migration rewrites the policy onto that
column with a FAIL-CLOSED rule:

    recipient_id = current_user           -- always enforced, never skippable
    AND (organization_id IS NULL          -- ONLY a deliberately global row
         OR organization_id = current_org)

A NULL ``organization_id`` is now an explicit, intentional state (genuinely
global platform/system or blog notifications) rather than an accident of a
missing JSON key. The recipient_id predicate keeps even global rows protected.

Rollback restores the previous metadata-based policy from ``0004``.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_CURRENT_USER = "NULLIF(current_setting('app.current_user_id', true), '')"
_EMPTY_JSONB = "'{}'::jsonb"

_TABLE = "notifications_inappnotification"

# ── New fail-closed policy (organization FK column) ────────────────────────
_NEW_CONDITION = (
    f"recipient_id::text = {_CURRENT_USER}\n"
    "        AND (\n"
    f"            organization_id IS NULL\n"
    f"            OR organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_BYPASS_EXPR}
        OR {_NEW_CONDITION}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_NEW_CONDITION}
    );
"""

# ── Reverse: restore the previous metadata-based (fail-open) policy ────────
_OLD_CONDITION = (
    f"recipient_id::text = {_CURRENT_USER}\n"
    "        AND (\n"
    f"            NULLIF(COALESCE(metadata, {_EMPTY_JSONB})->>'organization_id', '') IS NULL\n"
    f"            OR NULLIF(COALESCE(metadata, {_EMPTY_JSONB})->>'organization_id', '') = {_CURRENT_ORG}\n"
    "        )"
)

_REVERSE_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_BYPASS_EXPR}
        OR {_OLD_CONDITION}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_OLD_CONDITION}
    );
"""


def _apply_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FORWARD_SQL)


def _apply_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_expand_rls_scope"),
        ("notifications", "0003_inappnotification_organization"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse),
    ]
