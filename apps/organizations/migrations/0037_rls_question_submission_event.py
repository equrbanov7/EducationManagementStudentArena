"""``exams_questionsubmissionevent`` üçün RLS/FORCE RLS tenant izolyasiyası.

Hadisə lentində BİRBAŞA ``organization_id`` sütunu var (məhz bunun üçün model
tenant FK-sını daşıyır), ona görə sadə siyasət tətbiq olunur — nümunə
``apps/applications/migrations/0002_rls_applications.py``.  Postgres xaricində
no-op.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLE = "exams_questionsubmissionevent"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    );
"""

_REVERSE_SQL = f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0036_seed_question_chair_review"),
        ("exams", "0063_question_submission_chair_stage"),
    ]

    operations = [migrations.RunPython(_apply, _revert)]
