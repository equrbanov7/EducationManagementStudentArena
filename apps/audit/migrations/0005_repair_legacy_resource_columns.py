from django.db import migrations


LEGACY_INDEX_NAME = "audit_audit_resourc_2a3aef_idx"


def _ensure_legacy_resource_columns(apps, schema_editor):
    """
    Repair environments where the audit table drifted into the 0003 schema.

    This is intentionally idempotent so it can safely run after 0004 in healthy
    environments and only perform work when one of the legacy columns or its
    composite index is missing.
    """

    connection = schema_editor.connection
    table_name = "audit_auditlog"
    quote = schema_editor.quote_name

    with connection.cursor() as cursor:
        existing_tables = set(connection.introspection.table_names(cursor))
        if table_name not in existing_tables:
            return

        description = connection.introspection.get_table_description(cursor, table_name)
        columns = {connection.introspection.identifier_converter(column.name) for column in description}

        if "resource_type" not in columns:
            schema_editor.execute(
                f"ALTER TABLE {quote(table_name)} "
                f"ADD COLUMN {quote('resource_type')} varchar(100) NOT NULL DEFAULT '';"
            )
            columns.add("resource_type")

        if "resource_id" not in columns:
            schema_editor.execute(
                f"ALTER TABLE {quote(table_name)} "
                f"ADD COLUMN {quote('resource_id')} varchar(255) NOT NULL DEFAULT '';"
            )
            columns.add("resource_id")

        if "resource_repr" not in columns:
            schema_editor.execute(
                f"ALTER TABLE {quote(table_name)} "
                f"ADD COLUMN {quote('resource_repr')} varchar(500) NOT NULL DEFAULT '';"
            )
            columns.add("resource_repr")

        constraints = connection.introspection.get_constraints(cursor, table_name)
        if LEGACY_INDEX_NAME not in constraints and {"resource_type", "resource_id"}.issubset(columns):
            schema_editor.execute(
                f"CREATE INDEX {quote(LEGACY_INDEX_NAME)} "
                f"ON {quote(table_name)} ({quote('resource_type')}, {quote('resource_id')});"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0004_restore_legacy_resource_fields"),
    ]

    operations = [
        migrations.RunPython(
            _ensure_legacy_resource_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
