"""Açar düzəlişi cədvəllərinə RLS tenant izolyasiyası (2026-10-13, gecə).

* ``appeals_answerkeycorrection`` — BİRBAŞA ``organization_id`` (``appeals_appeal`` ilə eyni siyasət);
* ``appeals_keycorrectioncredit``  — DOLAYI, düzəliş başlığı üzərindən (``appeals_scoreadjustment`` kimi).

Nümunə: ``organizations.0007_rls_question_bank_appeals``. Yalnız PostgreSQL-də; geri alına bilir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_CORRECTION_ORG_SUBQUERY = (
    "correction_id IN (\n"
    "            SELECT id FROM appeals_answerkeycorrection\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_POLICIES = {
    "appeals_answerkeycorrection": f"organization_id::text = {_CURRENT_ORG}",
    "appeals_keycorrectioncredit": _CORRECTION_ORG_SUBQUERY,
}


def _policy(table, using):
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING ({_BYPASS_EXPR} OR {using})
    WITH CHECK ({_BYPASS_EXPR} OR {using});
"""


def _forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute("".join(_policy(table, using) for table, using in _POLICIES.items()))
    # Məhdud RLS rolu (testlər / prod) yeni cədvəllərə çıxış alsın — 0007 nümunəsi.
    schema_editor.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN "
        "GRANT ALL ON appeals_answerkeycorrection, appeals_keycorrectioncredit TO rls_app_role; "
        "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rls_app_role; END IF; END $$;"
    )


def _reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    for table in _POLICIES:
        schema_editor.execute(
            f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table};"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):

    dependencies = [("appeals", "0005_answer_key_correction")]

    operations = [migrations.RunPython(_forward, _reverse)]
