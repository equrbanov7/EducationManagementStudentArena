"""Index canonical email probes, including cross-field collision guards.

The existing UNIQUE index covers only nonblank emails. Login's two independent
username/email probes and the collision trigger cannot imply its predicate.
A full nonunique index preserves all existing identity semantics and guards.
"""

from django.db import migrations

INDEX = "accounts_auth_email_lookup_idx"


def add_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)",
            [INDEX],
        )
        row = cursor.fetchone()
        # Recover an interrupted concurrent build instead of silently keeping
        # its unusable index on the next migration attempt.
        if row and not row[0]:
            cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{INDEX}"')
        cursor.execute(
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{INDEX}" '
            'ON "auth_user" (LOWER(NORMALIZE(BTRIM(email), NFKC)))'
        )
        # Expression statistics are needed immediately: ORDER BY pk LIMIT 2
        # otherwise can still choose a full primary-key scan for absent emails.
        cursor.execute('ANALYZE "auth_user"')


def remove_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{INDEX}"')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("accounts", "0028_runtimesetting")]
    operations = [migrations.RunPython(add_index, remove_index)]
