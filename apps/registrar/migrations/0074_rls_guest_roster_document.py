"""RLS siyasəti — alt-qrup əlavəsinin sənədi (``registrar_guestrosterdocument``).

Audit `access` F-05 (2026-09-13): cədvəl 0069-da ``organization_id`` FK ilə
yaradılıb, amma digər düzəliş-sübut cədvəllərindən (0028/0031/0033/0035/0072)
fərqli olaraq RLS siyasəti YOX idi — klonda və sandbox-da ``organization_id``
daşıyıb siyasətsiz yeganə yeni tenant cədvəli. ORM oxusu enrollment id-ləri ilə
daralır və media prefiksi checker-lidir, yəni tətbiq qatında sızma yoxdur; bu,
müdafiə dərinliyi boşluğudur. ``0072_rls_exam_score_sheet`` ilə EYNİ naxış.
Postgres olmayan backend-də no-op. Əhatə testi:
``core/tests/test_audit_2026_09_13_rls_coverage.py`` (hər org-sütunlu cədvəlin
siyasəti olmalıdır — 0069 məhz belə test olmadığı üçün sürüşdü).
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = ["registrar_guestrosterdocument"]


def _forward_sql(table):
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    );
"""


def _reverse_sql(table):
    return f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_forward_sql(table))


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(_reverse_sql(table))


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0073_exam_score_sheet_integrity"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
