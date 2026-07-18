"""Index-back the RLS org predicate: functional index on ``(organization_id::text)``.

Every tenant-isolation policy filters rows with
``organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')``
(see ``organizations.0003`` and the later ``*_rls_*`` migrations). Casting the
UUID column to ``text`` means the existing b-tree index on ``organization_id``
cannot serve the predicate → a sequential scan on **every** org-filtered query.

Rather than rewrite ~40 security-sensitive RLS policies (tenant isolation is the
#1 invariant and there is no staging twin), this migration takes the zero-policy-
change path: it adds a **functional index on ``(organization_id::text)``** for
every table that (a) actually has an ``organization_id`` column and (b) carries an
RLS policy that references it. The planner then uses that index for the existing
predicate — same isolation semantics, no policy touched.

Self-discovering on purpose
---------------------------
The table set is read from the live catalog at apply time instead of hard-coded:

* it can never miss a table that has the column + policy, and
* it can never target a table that no longer exists / lacks the column
  (e.g. ``registrar_gradecomponent`` was dropped in ``registrar.0008`` and never
  recreated — a hard-coded list would try to index it and fail).

Indexes are built ``CONCURRENTLY`` (non-blocking on populated production tables),
so this migration is ``atomic = False``. No-op on non-PostgreSQL backends.
"""

from django.db import migrations

_INDEX_SUFFIX = "_org_txt_idx"

# Discover every base table that has a real ``organization_id`` column AND an RLS
# policy whose USING/WITH CHECK expression references ``organization_id`` (the
# direct-org tenant predicate). Indirect tables (scoped via a subquery, no own
# ``organization_id`` column) are naturally excluded by the column check. Join to
# ``pg_policy`` via the table's regclass so ``pg_get_expr`` can pretty-print the
# qual/with_check expression trees.
_DISCOVER_SQL = """
SELECT c.table_name
FROM information_schema.columns c
JOIN pg_catalog.pg_class rel
  ON rel.relname = c.table_name
 AND rel.relnamespace = 'public'::regnamespace
WHERE c.table_schema = 'public'
  AND c.column_name = 'organization_id'
  AND EXISTS (
      SELECT 1
      FROM pg_catalog.pg_policy pol
      WHERE pol.polrelid = rel.oid
        AND (
            COALESCE(pg_catalog.pg_get_expr(pol.polqual, pol.polrelid), '') LIKE '%organization_id%'
            OR COALESCE(pg_catalog.pg_get_expr(pol.polwithcheck, pol.polrelid), '') LIKE '%organization_id%'
        )
  )
ORDER BY c.table_name
"""


def _index_name(table: str) -> str:
    # Postgres identifiers cap at 63 chars; the longest current table
    # ("notifications_studentorganizationrequest") + suffix stays well under.
    return f"{table}{_INDEX_SUFFIX}"


def _discover_tables(cursor) -> list[str]:
    cursor.execute(_DISCOVER_SQL)
    return [row[0] for row in cursor.fetchall()]


def _create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        tables = _discover_tables(cursor)
    for table in tables:
        name = _index_name(table)
        schema_editor.execute(
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" ON "{table}" ((organization_id::text))'
        )


def _drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        tables = _discover_tables(cursor)
    for table in tables:
        name = _index_name(table)
        schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')


class Migration(migrations.Migration):
    # CONCURRENTLY index builds cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("organizations", "0024_membership_membership_user_org_active_idx"),
        # Ensure every app whose tables carry a direct-org RLS policy has created
        # both the table and its policy before we discover + index them.
        ("registrar", "0026_rls_kollokvium_window"),
        ("exams", "0058_examroomcomputer_roomcomp_org_mac_idx_and_more"),
        ("appeals", "0003_alter_appeal_status_alter_appealitem_appeal_type_and_more"),
        ("notifications", "0003_inappnotification_organization"),
    ]

    operations = [
        migrations.RunPython(_create_indexes, _drop_indexes),
    ]
