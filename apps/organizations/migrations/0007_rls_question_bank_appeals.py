"""RLS policies for the exam-system redesign tables (FAZA 3.1).

Adds PostgreSQL Row-Level Security tenant isolation for the new org-scoped
tables introduced by the exam-system redesign:

- ``exams_examlanguagevariant``  — indirect via ``exams_exam`` (like attempt).
- ``exams_questionbank``         — direct, NULLABLE org (legacy banks have NULL
                                   org until backfilled → NULL rows allowed
                                   globally, mirroring ``exams_studentgroup``).
- ``exams_bankquestion``         — indirect via the bank (NULL-org aware).
- ``exams_bankquestionoption``   — indirect via question → bank (NULL-org aware).
- ``appeals_appeal``             — direct, NON-NULL org.
- ``appeals_appealitem``         — indirect via appeal.
- ``appeals_scoreadjustment``    — indirect via appeal_item → appeal.

Pattern mirrors organizations.0003. Each CREATE is preceded by DROP POLICY IF
EXISTS so the migration is safe to re-apply. No-op on non-PostgreSQL backends.

Once every ``QuestionBank`` row carries an ``organization`` (data backfill), a
follow-up migration can tighten the bank policies to fail-closed (drop the
``organization_id IS NULL`` branch).
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"


def _policy(table: str, using: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {using}
    )
    WITH CHECK (
        {using}
    );
"""


def _direct(table: str) -> str:
    return _policy(table, f"{_BYPASS_EXPR}\n        OR {_ORG_EXPR}")


def _direct_nullable(table: str) -> str:
    return _policy(table, f"{_BYPASS_EXPR}\n        OR organization_id IS NULL\n        OR {_ORG_EXPR}")


def _indirect(table: str, subquery: str) -> str:
    return _policy(table, f"{_BYPASS_EXPR}\n        OR {subquery}")


# ── Subquery fragments ─────────────────────────────────────────────────────
_EXAM_ORG_SUBQUERY = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

# Bank org is nullable (legacy banks). Allow NULL-org banks globally.
_BANK_ORG_SUBQUERY = (
    "bank_id IN (\n"
    "            SELECT id FROM exams_questionbank\n"
    f"            WHERE organization_id IS NULL OR organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_BANKQUESTION_ORG_SUBQUERY = (
    "question_id IN (\n"
    "            SELECT bq.id FROM exams_bankquestion bq\n"
    "            JOIN exams_questionbank qb ON qb.id = bq.bank_id\n"
    f"            WHERE qb.organization_id IS NULL OR qb.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_APPEAL_ORG_SUBQUERY = (
    "appeal_id IN (\n"
    "            SELECT id FROM appeals_appeal\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_APPEALITEM_ORG_SUBQUERY = (
    "appeal_item_id IN (\n"
    "            SELECT ai.id FROM appeals_appealitem ai\n"
    "            JOIN appeals_appeal a ON a.id = ai.appeal_id\n"
    f"            WHERE a.organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_TABLES = [
    "exams_examlanguagevariant",
    "exams_questionbank",
    "exams_bankquestion",
    "exams_bankquestionoption",
    "appeals_appeal",
    "appeals_appealitem",
    "appeals_scoreadjustment",
]

_FORWARD_SQL = (
    _indirect("exams_examlanguagevariant", _EXAM_ORG_SUBQUERY)
    + _direct_nullable("exams_questionbank")
    + _indirect("exams_bankquestion", _BANK_ORG_SUBQUERY)
    + _indirect("exams_bankquestionoption", _BANKQUESTION_ORG_SUBQUERY)
    + _direct("appeals_appeal")
    + _indirect("appeals_appealitem", _APPEAL_ORG_SUBQUERY)
    + _indirect("appeals_scoreadjustment", _APPEALITEM_ORG_SUBQUERY)
)

_REVERSE_SQL = "\n".join(
    f"DROP POLICY IF EXISTS rls_tenant_isolation ON {t};\n"
    f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;"
    for t in _TABLES
)


def _apply_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FORWARD_SQL)
    # Ensure the restricted RLS role can access the new tables/sequences.
    schema_editor.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO rls_app_role")
    schema_editor.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rls_app_role")


def _apply_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0006_migrate_legacy_permission_aliases"),
        ("exams", "0017_question_bank_library"),
        ("appeals", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse),
    ]
