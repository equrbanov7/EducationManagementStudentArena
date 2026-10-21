"""Apellyasiya qərar yazısı cədvəlinə RLS tenant izolyasiyası (2026-10-21).

``appeals_appealdecisionrecord`` — BİRBAŞA ``organization_id`` (``appeals_appeal`` ilə eyni siyasət).
Nümunə: ``0006_rls_answer_key_correction``. Yalnız PostgreSQL-də; geri alına bilir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_TABLE = "appeals_appealdecisionrecord"
_USING = f"organization_id::text = {_CURRENT_ORG}"


def _forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(
        f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING ({_BYPASS_EXPR} OR {_USING})
    WITH CHECK ({_BYPASS_EXPR} OR {_USING});
"""
    )
    schema_editor.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN "
        f"GRANT ALL ON {_TABLE} TO rls_app_role; "
        "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rls_app_role; END IF; END $$;"
    )


def _reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(
        f"DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};"
        f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;"
        f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
    )


class Migration(migrations.Migration):

    dependencies = [("appeals", "0008_decision_teacher_and_record")]

    operations = [migrations.RunPython(_forward, _reverse)]
