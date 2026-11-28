from django.db import migrations

TABLES = (
    "journalwatchrecipient",
    "journalwatch",
    "journalwatchevent",
    "journalwatchroute",
    "journalwatchbatch",
    "journalwatchmailitem",
)
# Existing UUID primary keys stay the canonical object identifiers. Composite foreign keys
# additionally prevent cross-tenant routes and delivery rows, even on administrative writes.
TARGETS = {
    "journalwatch": "id, organization_id",
    "journalwatchrecipient": "id, organization_id",
    "journalwatchevent": "id, organization_id",
    "journalwatchbatch": "id, recipient_id, organization_id",
}
REFERENCES = (
    ("journalwatchroute", "jw_route_watch_org", "watch_id, organization_id", "journalwatch"),
    ("journalwatchroute", "jw_route_recipient_org", "recipient_id, organization_id", "journalwatchrecipient"),
    ("journalwatchbatch", "jw_batch_recipient_org", "recipient_id, organization_id", "journalwatchrecipient"),
    ("journalwatchmailitem", "jw_item_event_org", "event_id, organization_id", "journalwatchevent"),
    ("journalwatchmailitem", "jw_item_batch_org", "batch_id, recipient_id, organization_id", "journalwatchbatch"),
)


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    condition = "current_setting('app.bypass_rls', true) = 'on' OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"
    for name in TABLES:
        table = f"monitoring_{name}"
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table}")
        schema_editor.execute(
            f"CREATE POLICY rls_tenant_isolation ON {table} USING ({condition}) WITH CHECK ({condition})"
        )
    for name, cols in TARGETS.items():
        schema_editor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS jw_{name}_tenant ON monitoring_{name} ({cols})")
    for name, c, cols, ref in REFERENCES:
        schema_editor.execute(f"ALTER TABLE monitoring_{name} DROP CONSTRAINT IF EXISTS {c}")
        schema_editor.execute(
            f"ALTER TABLE monitoring_{name} ADD CONSTRAINT {c} FOREIGN KEY ({cols}) REFERENCES monitoring_{ref} ({TARGETS[ref]}) DEFERRABLE INITIALLY DEFERRED"
        )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, c, _, _ in REFERENCES:
        schema_editor.execute(f"ALTER TABLE monitoring_{name} DROP CONSTRAINT IF EXISTS {c}")
    for name in TARGETS:
        schema_editor.execute(f"DROP INDEX IF EXISTS jw_{name}_tenant")
    for name in TABLES:
        table = f"monitoring_{name}"
        schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("monitoring", "0003_journal_watch")]
    operations = [migrations.RunPython(forward, reverse)]
