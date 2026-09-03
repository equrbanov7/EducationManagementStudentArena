"""``registrar_studentmovement`` üçün RLS + APPEND-ONLY qoruması.

İki qat, ikisi də DB-tərəfdir (tətbiq qatının qapısı
``ImmutableCorrectionEvidence``-dədir — o, yalnız ORM instansiyalarını tutur):

1. **RLS / FORCE RLS** — cədvəldə birbaşa ``organization_id`` var, ona görə
   sadə tenant siyasəti (nümunə: ``apps/applications/migrations/0002_rls_applications.py``).
2. **Append-only trigger** — UPDATE və DELETE bloklanır. Hərəkət əmri rəsmi
   sənəddir: yazıldıqdan sonra nə düzəldilir, nə də silinir (handoff §8/5).
   Səhv yazılmış əmr YENİ əmrlə (məs. «Bərpa») düzəldilir; audit izi qalır.
   Superuser trigger-i müvəqqəti söndürərək qanuni retention əməliyyatı apara
   bilər — ``audit_auditlog`` ilə eyni model (0019 migrasiyası).

Qeyri-PostgreSQL backend-lərdə no-op; geri qaytarıla bilir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLE = "registrar_studentmovement"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    )
    WITH CHECK (
        {_BYPASS_EXPR}
        OR {_ORG_EXPR}
    );

CREATE OR REPLACE FUNCTION emsarena_student_movement_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'registrar_studentmovement append-only: % qadağandır', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS student_movement_no_update ON {_TABLE};
CREATE TRIGGER student_movement_no_update
    BEFORE UPDATE ON {_TABLE}
    FOR EACH ROW EXECUTE FUNCTION emsarena_student_movement_append_only();

DROP TRIGGER IF EXISTS student_movement_no_delete ON {_TABLE};
CREATE TRIGGER student_movement_no_delete
    BEFORE DELETE ON {_TABLE}
    FOR EACH ROW EXECUTE FUNCTION emsarena_student_movement_append_only();
"""

_REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS student_movement_no_update ON {_TABLE};
DROP TRIGGER IF EXISTS student_movement_no_delete ON {_TABLE};
DROP FUNCTION IF EXISTS emsarena_student_movement_append_only();
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # ⚠️ `params=None` MƏCBURİDİR: plpgsql gövdəsindəki `%` (RAISE EXCEPTION
    # format spesifikatoru) əks halda psycopg-nin parametr interpolyasiyasına
    # düşür və miqrasiya (deməli, HƏR test bazasının qurulması) çökür.
    # Eyni tələ: `apps/workload/migrations/0002_rls_workload.py`.
    schema_editor.execute(_FORWARD_SQL, params=None)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [("registrar", "0066_student_movement_and_admission_fields")]

    operations = [migrations.RunPython(_apply, _revert)]
