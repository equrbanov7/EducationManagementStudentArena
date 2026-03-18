from django.db import migrations


def _set_legacy_column_defaults(apps, schema_editor):
    """
    Add database-level DEFAULT '' to the three legacy VARCHAR columns so that
    any INSERT issued by application code that was deployed *before* this
    migration has been applied does not trigger a NOT NULL violation.

    Only runs on PostgreSQL; SQLite (test runner) does not need it because
    SQLite does not enforce NOT NULL constraints at the engine level in the
    same way and supports neither the syntax nor the need.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "ALTER TABLE audit_auditlog "
        "ALTER COLUMN resource_type SET DEFAULT '', "
        "ALTER COLUMN resource_id SET DEFAULT '', "
        "ALTER COLUMN resource_repr SET DEFAULT '';"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_auditlog_audit_audit_resourc_2a3aef_idx_and_more"),
    ]

    operations = [
        # Set DB-level defaults so that any INSERT issued by new application code
        # (which no longer references these columns) does not trigger a NOT NULL
        # violation during the deployment window before this migration is applied.
        migrations.RunPython(
            _set_legacy_column_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="auditlog",
            name="audit_audit_resourc_2a3aef_idx",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_type",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_id",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_repr",
        ),
    ]
