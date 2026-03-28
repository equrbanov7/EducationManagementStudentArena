"""
Migration: Enable PostgreSQL Row-Level Security on tenant-aware tables.

This migration activates RLS for every critical table that stores
organisation-scoped data.  On non-PostgreSQL backends (e.g. SQLite in local
development) the migration is a harmless no-op.

Each table receives exactly one permissive policy named
``rls_tenant_isolation``.  The policy grants row visibility when **either**:

* ``app.bypass_rls`` session variable equals ``'on'``  (superadmin / migration
  bypass), **or**
* the row's organisation matches the value stored in ``app.current_org_id``
  (set by :class:`apps.organizations.middleware.OrganizationMiddleware`).

Tables whose organisation relationship is indirect (e.g. Assignment → Course →
Organisation) use a subquery in the ``USING`` / ``WITH CHECK`` clauses so the
policy still works without adding redundant FK columns.

Rollback plan
-------------
The reverse operation drops all policies and disables (and un-forces) RLS on
every table, fully reverting to the pre-RLS state.

Security note
-------------
``FORCE ROW LEVEL SECURITY`` is applied so that the application's database
user — who is typically the table owner — is also subject to RLS.  The only
exception is a PostgreSQL *superuser*, which always bypasses RLS at the engine
level.  Granting superuser only to a dedicated DBA/migration role (not the
application role) is the recommended production setup.
"""

from django.db import migrations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_ORG_EXPR = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"


def _direct_org_policy(table: str) -> str:
    """Return the full SQL block for a table with a direct ``organization_id`` FK."""
    using = f"{_BYPASS_EXPR}\n        OR {_ORG_EXPR}"
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {using}
    )
    WITH CHECK (
        {using}
    );
"""


def _indirect_org_policy(table: str, subquery: str) -> str:
    """Return the full SQL block for a table whose org relationship is indirect.

    Args:
        table:    Target table name.
        subquery: A SQL expression that evaluates to ``true`` when the row
                  belongs to the active tenant, e.g.
                  ``"course_id IN (SELECT id FROM courses_course WHERE ...)"``.
    """
    using = f"{_BYPASS_EXPR}\n        OR {subquery}"
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {using}
    )
    WITH CHECK (
        {using}
    );
"""


# Subquery fragment re-used by every table that goes through courses_course.
_COURSE_ORG_SUBQUERY = (
    "course_id IN (\n"
    "            SELECT id FROM courses_course\n"
    "            WHERE organization_id::text"
    " = NULLIF(current_setting('app.current_org_id', true), '')\n"
    "        )"
)

# Subquery fragment for tables that go through assignments_assignment → course.
_ASSIGNMENT_ORG_SUBQUERY = (
    "assignment_id IN (\n"
    "            SELECT a.id FROM assignments_assignment a\n"
    "            JOIN courses_course c ON c.id = a.course_id\n"
    "            WHERE c.organization_id::text"
    " = NULLIF(current_setting('app.current_org_id', true), '')\n"
    "        )"
)

# Subquery fragment for tables that go through exams_exam.
_EXAM_ORG_SUBQUERY = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    "            WHERE organization_id::text"
    " = NULLIF(current_setting('app.current_org_id', true), '')\n"
    "        )"
)

# Subquery fragment for live_exam tables that go through live_exam_livesession.
_SESSION_ORG_SUBQUERY = (
    "session_id IN (\n"
    "            SELECT s.id FROM live_exam_livesession s\n"
    "            JOIN exams_exam e ON e.id = s.exam_id\n"
    "            WHERE e.organization_id::text"
    " = NULLIF(current_setting('app.current_org_id', true), '')\n"
    "        )"
)

# StudentGroup has a nullable organization_id: NULL rows are treated as
# globally accessible (not tenant-scoped), so the policy also permits them.
_STUDENT_GROUP_USING = f"{_BYPASS_EXPR}\n        OR organization_id IS NULL\n        OR {_ORG_EXPR}"

# ---------------------------------------------------------------------------
# Forward migration SQL
# ---------------------------------------------------------------------------

_FORWARD_SQL = (
    # ── Organisation tables ──────────────────────────────────────────────
    _direct_org_policy("organizations_orgunit")
    + _direct_org_policy("organizations_academicperiod")
    + _direct_org_policy("organizations_role")
    + _direct_org_policy("organizations_membership")
    # ── Course tables ────────────────────────────────────────────────────
    + _direct_org_policy("courses_course")
    + _indirect_org_policy("courses_coursemembership", _COURSE_ORG_SUBQUERY)
    + _indirect_org_policy("courses_coursetopic", _COURSE_ORG_SUBQUERY)
    + _indirect_org_policy("courses_courseresource", _COURSE_ORG_SUBQUERY)
    + _indirect_org_policy("courses_courseinstructor", _COURSE_ORG_SUBQUERY)
    + _indirect_org_policy("courses_coursegroup", _COURSE_ORG_SUBQUERY)
    # ── Exam tables ──────────────────────────────────────────────────────
    + _direct_org_policy("exams_exam")
    + _indirect_org_policy("exams_examattempt", _EXAM_ORG_SUBQUERY)
    # StudentGroup: nullable organization_id — allow NULL rows globally
    + f"""
ALTER TABLE exams_studentgroup ENABLE ROW LEVEL SECURITY;
ALTER TABLE exams_studentgroup FORCE ROW LEVEL SECURITY;
CREATE POLICY rls_tenant_isolation ON exams_studentgroup
    USING (
        {_STUDENT_GROUP_USING}
    )
    WITH CHECK (
        {_STUDENT_GROUP_USING}
    );
"""
    # ── Assignment tables ────────────────────────────────────────────────
    + _indirect_org_policy("assignments_assignment", _COURSE_ORG_SUBQUERY)
    + _indirect_org_policy("assignments_submission", _ASSIGNMENT_ORG_SUBQUERY)
    # ── Lab tables ───────────────────────────────────────────────────────
    + _indirect_org_policy("labs_lab", _COURSE_ORG_SUBQUERY)
    # ── Notification tables ──────────────────────────────────────────────
    + _direct_org_policy("notifications_studentorganizationrequest")
    # ── Live exam tables ─────────────────────────────────────────────────
    + _indirect_org_policy("live_exam_livesession", _EXAM_ORG_SUBQUERY)
    + _indirect_org_policy("live_exam_liveplayer", _SESSION_ORG_SUBQUERY)
    + _indirect_org_policy("live_exam_liveanswer", _SESSION_ORG_SUBQUERY)
)

# ---------------------------------------------------------------------------
# Reverse (rollback) SQL
# ---------------------------------------------------------------------------

_TABLES = [
    "organizations_orgunit",
    "organizations_academicperiod",
    "organizations_role",
    "organizations_membership",
    "courses_course",
    "courses_coursemembership",
    "courses_coursetopic",
    "courses_courseresource",
    "courses_courseinstructor",
    "courses_coursegroup",
    "exams_exam",
    "exams_examattempt",
    "exams_studentgroup",
    "assignments_assignment",
    "assignments_submission",
    "labs_lab",
    "notifications_studentorganizationrequest",
    "live_exam_livesession",
    "live_exam_liveplayer",
    "live_exam_liveanswer",
]

_REVERSE_SQL = "\n".join(
    f"DROP POLICY IF EXISTS rls_tenant_isolation ON {t};\n"
    f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;"
    for t in _TABLES
)

# ---------------------------------------------------------------------------
# RunPython callbacks — skips non-PostgreSQL (e.g. SQLite in dev)
# ---------------------------------------------------------------------------


def _apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # Bypass RLS for the duration of this migration transaction so that the
    # ALTER TABLE / CREATE POLICY statements themselves are not restricted.
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FORWARD_SQL)
    # Create a restricted application role used for RLS enforcement.
    # This role is non-superuser so PostgreSQL RLS policies apply to it.
    # In production the application connects as a dedicated non-superuser DB
    # user (RLS is then enforced automatically).  In test environments where
    # the test runner uses a superuser account, tests can switch to this role
    # via ``SET LOCAL ROLE rls_app_role`` to exercise the RLS policies.
    schema_editor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_roles WHERE rolname = 'rls_app_role'
            ) THEN
                CREATE ROLE rls_app_role NOSUPERUSER NOLOGIN;
            END IF;
        END
        $$
        """)
    schema_editor.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO rls_app_role")
    schema_editor.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO rls_app_role")
    # Ensure future tables created by subsequent migrations are also accessible.
    schema_editor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public " "GRANT ALL ON TABLES TO rls_app_role")
    schema_editor.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public " "GRANT ALL ON SEQUENCES TO rls_app_role")


def _rollback_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_REVERSE_SQL)
    schema_editor.execute("DROP ROLE IF EXISTS rls_app_role")


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0002_seed_azerbaijan_country"),
        ("courses", "0001_initial"),
        ("exams", "0001_initial"),
        ("assignments", "0001_initial"),
        ("notifications", "0002_add_role_type_to_org_request"),
        ("live_exam", "0001_initial"),
        ("labs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply_rls, _rollback_rls),
    ]
