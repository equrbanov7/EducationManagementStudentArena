"""audit_auditlog attribution tamper qorunması (re-audit §5.5).

0019 append-only trigger-i FK sütunlarını (user_id/organization_id/
content_type_id) müqayisədən BÜTÖVLÜKDƏ çıxarmışdı ki, ``ON DELETE SET NULL``
FK-nullification-ı bloklanmasın. Nəticədə ``user_id`` A→B YENİDƏN təyin edilə
bilirdi (attribution tamper). Bu migration UPDATE trigger funksiyasını
``CREATE OR REPLACE`` ilə sərtləşdirir: FK dəyişikliyinə YALNIZ real silmə
(``OLD.fk IS NOT NULL AND NEW.fk IS NULL``) halında icazə verilir; başqa
dəyəri (o cümlədən A→B) reject olunur. DELETE tam bloklu qalır.

Qeyri-PostgreSQL backend-lərdə no-op; geri qaytarıla bilir (0019 funksiyasına).
"""

from django.db import migrations

_HARDENED_SQL = """
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
        -- FK dəyişikliyinə YALNIZ NULL-a keçid (ON DELETE SET NULL) icazəlidir.
        -- A→B (və ya NULL→X) yenidən təyin attribution tamper-dir → reject.
        OR (NEW.user_id IS DISTINCT FROM OLD.user_id AND NEW.user_id IS NOT NULL)
        OR (NEW.organization_id IS DISTINCT FROM OLD.organization_id AND NEW.organization_id IS NOT NULL)
        OR (NEW.content_type_id IS DISTINCT FROM OLD.content_type_id AND NEW.content_type_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'audit_auditlog append-only: məzmun/attribution UPDATE qadağandır';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Geri qaytarma: 0019-dakı yalnız-məzmun variantına qayıt (FK dəyişikliyinə icazə).
_REVERT_SQL = """
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
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_HARDENED_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERT_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0020_rls_cross_fk_hardening"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
