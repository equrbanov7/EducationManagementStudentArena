"""audit_auditlog append-only / tamper-evident (audit layihə-wide P1 #5).

Audit log tamper-evidence tələb edir: tətbiq (və ya kompromis olmuş app rolu)
keçmiş audit sətrini DƏYİŞMƏ və ya SİLMƏ imkanına malik olmamalıdır. Bunu
DB-tərəf trigger ilə tətbiq edirik — həm app rolu, həm də owner rolu üçün
UPDATE/DELETE bloklanır (yalnız INSERT və SELECT). Superuser trigger-i disable
edərək qanuni miqrasiya/retention əməliyyatı apara bilər.

Qeyri-PostgreSQL backend-lərdə no-op; geri qaytarıla bilir.
"""

from django.db import migrations

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION emsarena_audit_log_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog append-only: UPDATE/DELETE qadağandır';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_auditlog;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION emsarena_audit_log_immutable();

DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_auditlog;
CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION emsarena_audit_log_immutable();
"""

_REVERSE_SQL = """
DROP TRIGGER IF EXISTS audit_log_no_update ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_auditlog;
DROP FUNCTION IF EXISTS emsarena_audit_log_immutable();
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
        ("organizations", "0018_rls_labs_projects"),
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
