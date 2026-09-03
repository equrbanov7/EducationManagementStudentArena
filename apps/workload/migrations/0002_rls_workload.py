"""Dərs yükü cədvəlləri: RLS/FORCE RLS + saat balansı + append-only qorumaları.

ÜÇ QAT (hamısı yalnız PostgreSQL-də; sqlite-da no-op):

1. **RLS tenant izolyasiyası** — beş cədvəlin hamısında BİRBAŞA ``organization_id``
   FK var, ona görə eyni sadə siyasət tətbiq olunur (``syllabus.0002_rls_syllabus``
   nümunəsi).
2. **Saat balansı trigger-i** — ``Σ TeacherAssignment.hours ≤`` sətrin həmin
   fəaliyyət üzrə cəmi. Servis qatı bunu ``select_for_update`` ilə onsuz da
   yoxlayır; trigger servisi YAN KEÇƏN hər yolu (admin, shell, gələcək idxal)
   bağlayır. Fəaliyyət → sütun xəritəsi ``constants.ACTIVITY_TOTAL_FIELD`` ilə
   EYNİ olmalıdır — yeni fəaliyyət əlavə edəndə hər iki yer yenilənir.
3. **Append-only düzəliş reyestri** — ``workload_workloadamendment`` sətri
   yaradıldıqdan sonra UPDATE/DELETE qadağandır (``made_by``/``organization``
   ON DELETE SET NULL üçün istisna yoxdur, çünki hər iki FK SET_NULL-dur və
   yalnız sütun dəyişir — ona görə FK təmizliyi üçün nəzarətli istisna var).
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_TABLES = [
    "workload_teachingtask",
    "workload_teachingtaskrow",
    "workload_teacherassignment",
    "workload_teacherworkloadprofile",
    "workload_workloadamendment",
]


def _rls_forward(table):
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


def _rls_reverse(table):
    return f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


_BALANCE_SQL = """
CREATE OR REPLACE FUNCTION workload_assignment_balance_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    cap integer;
    used integer;
BEGIN
    SELECT CASE NEW.activity
        WHEN 'lecture' THEN row_.lecture_total
        WHEN 'seminar' THEN row_.seminar_total
        WHEN 'lab' THEN row_.lab_total
        WHEN 'consult' THEN row_.consult_hours
        WHEN 'exam' THEN row_.exam_hours
        WHEN 'thesis' THEN row_.thesis_hours
        WHEN 'postgrad' THEN row_.postgrad_hours
        WHEN 'practice_research' THEN row_.practice_research_hours
        WHEN 'practice_production' THEN row_.practice_production_hours
        ELSE 0
    END
    INTO cap
    FROM workload_teachingtaskrow AS row_
    WHERE row_.id = NEW.row_id;

    IF cap IS NULL THEN
        cap := 0;
    END IF;

    SELECT COALESCE(SUM(hours), 0) INTO used
    FROM workload_teacherassignment
    WHERE row_id = NEW.row_id
      AND activity = NEW.activity
      AND id <> NEW.id;

    IF used + NEW.hours > cap THEN
        RAISE EXCEPTION
            'workload_hour_balance_exceeded: activity=% cap=% used=% new=%',
            NEW.activity, cap, used, NEW.hours;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workload_assignment_balance ON workload_teacherassignment;
CREATE TRIGGER workload_assignment_balance
BEFORE INSERT OR UPDATE ON workload_teacherassignment
FOR EACH ROW
EXECUTE FUNCTION workload_assignment_balance_guard();
"""

_BALANCE_REVERSE = """
DROP TRIGGER IF EXISTS workload_assignment_balance ON workload_teacherassignment;
DROP FUNCTION IF EXISTS workload_assignment_balance_guard();
"""

_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION workload_amendment_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.id IS NOT DISTINCT FROM NEW.id
       AND OLD.task_id IS NOT DISTINCT FROM NEW.task_id
       AND OLD.target_kind IS NOT DISTINCT FROM NEW.target_kind
       AND OLD.target_id IS NOT DISTINCT FROM NEW.target_id
       AND OLD.reason IS NOT DISTINCT FROM NEW.reason
       AND OLD.note IS NOT DISTINCT FROM NEW.note
       AND OLD.old_values IS NOT DISTINCT FROM NEW.old_values
       AND OLD.new_values IS NOT DISTINCT FROM NEW.new_values
       AND OLD.created_at IS NOT DISTINCT FROM NEW.created_at
       AND OLD.made_by_id IS NOT NULL
       AND NEW.made_by_id IS NULL
    THEN
        -- Yeganə icazəli UPDATE: `made_by` istifadəçisi silinəndə FK-nın
        -- ON DELETE SET NULL davranışı (qeydin özü qorunur).
        RETURN NEW;
    END IF;

    RAISE EXCEPTION USING MESSAGE =
        'workload_workloadamendment append-only: ' || TG_OP || ' qadağandır';
END;
$$;

DROP TRIGGER IF EXISTS workload_amendment_append_only ON workload_workloadamendment;
CREATE TRIGGER workload_amendment_append_only
BEFORE UPDATE OR DELETE ON workload_workloadamendment
FOR EACH ROW
EXECUTE FUNCTION workload_amendment_append_only_guard();
"""

_APPEND_ONLY_REVERSE = """
DROP TRIGGER IF EXISTS workload_amendment_append_only ON workload_workloadamendment;
DROP FUNCTION IF EXISTS workload_amendment_append_only_guard();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        # ⚠️ `params=None` MƏCBURİDİR: plpgsql gövdəsindəki `%` (RAISE EXCEPTION
        # format spesifikatorları) psycopg-nin parametr interpolyasiyasına düşür və
        # `IndexError: tuple index out of range` verir. `None` interpolyasiyanı
        # tam söndürür.
        schema_editor.execute(_rls_forward(table), params=None)
    schema_editor.execute(_BALANCE_SQL, params=None)
    schema_editor.execute(_APPEND_ONLY_SQL, params=None)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_APPEND_ONLY_REVERSE, params=None)
    schema_editor.execute(_BALANCE_REVERSE, params=None)
    for table in _TABLES:
        schema_editor.execute(_rls_reverse(table), params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
