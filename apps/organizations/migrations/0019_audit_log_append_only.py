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
-- UPDATE: yalnız MƏZMUN sütunları dəyişəndə blokla. user_id/organization_id/
-- content_type_id NULL-a keçidinə (ON DELETE SET NULL — istinad edilən
-- user/org/content_type silinəndə audit sətri qorunur, FK NULL olur) İCAZƏ
-- verilir; əks halda user silmək mümkün olmazdı və audit tarixçəsi itərdi.
CREATE OR REPLACE FUNCTION emsarena_audit_log_no_content_update()
RETURNS trigger AS $$
BEGIN
    IF (
        NEW.action IS DISTINCT FROM OLD.action
        OR NEW.resource_type IS DISTINCT FROM OLD.resource_type
        OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
        OR NEW.resource_repr IS DISTINCT FROM OLD.resource_repr
        OR NEW.object_id IS DISTINCT FROM OLD.object_id
        OR NEW.old_values IS DISTINCT FROM OLD.old_values
        OR NEW.new_values IS DISTINCT FROM OLD.new_values
        OR NEW.changes IS DISTINCT FROM OLD.changes
        OR NEW.reason IS DISTINCT FROM OLD.reason
        OR NEW.ip_address IS DISTINCT FROM OLD.ip_address
        OR NEW.user_agent IS DISTINCT FROM OLD.user_agent
        OR NEW.request_id IS DISTINCT FROM OLD.request_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'audit_auditlog append-only: məzmun UPDATE qadağandır';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- DELETE: heç vaxt icazə verilmir (append-only).
CREATE OR REPLACE FUNCTION emsarena_audit_log_no_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog append-only: DELETE qadağandır';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_auditlog;
CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION emsarena_audit_log_no_content_update();

DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_auditlog;
CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION emsarena_audit_log_no_delete();
"""

_REVERSE_SQL = """
DROP TRIGGER IF EXISTS audit_log_no_update ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_auditlog;
DROP FUNCTION IF EXISTS emsarena_audit_log_no_content_update();
DROP FUNCTION IF EXISTS emsarena_audit_log_no_delete();
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
