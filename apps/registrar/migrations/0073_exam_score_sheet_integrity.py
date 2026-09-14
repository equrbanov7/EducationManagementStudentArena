"""``ExamScoreSheet`` ↔ açılış ↔ sətir əlaqələrinin DB-səviyyə qorunması (Codex audit P2-09, 2026-09-13).

Codex (2026-09-12, §9): «yeni bal vərəqinin tenant/offering əlaqəsi servis
səviyyəsində qorunur; bütün əlaqələr üçün ayrıca DB trigger attestasiya
olunmayıb». Servis qatı (``exam_score_sheets.create_sheet`` /
``exam_score_entry.record_exam_score``) yeganə yazı yolu olsa da, xam SQL,
``QuerySet.update()`` və gələcək kod üçün invariantlar burada PostgreSQL
trigger-ləri ilə təkrarlanır (``0041`` ``registrar_guard_*`` nümunəsi):

I1  ``registrar_examscoresheet.organization_id`` = açılışın ``organization_id``-si;
    vərəqin (təşkilat, açılış) kimliyi yaradıldıqdan sonra DƏYİŞMİR — əks halda
    artıq bağlanmış sətirlər səssizcə başqa açılışa düşərdi (sayğac və skan
    yeniləmələri sərbəstdir).
I3  ``registrar_examscoreentry``: sətrin təşkilatı qeydiyyatın təşkilatı ilə
    eynidir; ``sheet_id`` doludursa vərəq sətrin təşkilatına VƏ qeydiyyatın
    açılışına aiddir.
I4  ``registrar_examscoresheet.evidence`` doludursa
    ``exam_score_sheets/<organization_id>/`` prefiksi altındadır — media checker
    (``core.media_policies.check_exam_score_sheet_access``) təşkilatı sətirdən
    oxuyur; yol başqa tenantın prefiksinə işarə edə bilməz.

I2 (``examiner`` aktiv üzvlük) QƏSDƏN DB-də yoxlanmır: üzvlüklər dəyişir, vərəq
isə tarixi snapshot-dur; servis qatında (``create_sheet``) yoxlanılır, açılışın
öz müəllimi isə onsuz da ``0041`` ``registrar_active_member_instructor_guard``
ilə təsdiqlənib.

Model qatı eyni qaydaları ``clean()``-də təkrarlayır ki, adi axında xəta
``ValidationError`` kimi trigger-dən ƏVVƏL üzə çıxsın. Mövcud pozuntu varsa
migrasiya (``0041`` fəlsəfəsi ilə) DAYANIR — akademik sətir yenidən yazılmır.
Qeyri-PostgreSQL backend-də no-op; geri qaytarıla bilir.
"""

from django.db import migrations

_SHEET_TABLE = "registrar_examscoresheet"
_ENTRY_TABLE = "registrar_examscoreentry"
_SHEET_TRIGGER = "registrar_exam_score_sheet_integrity_guard"
_ENTRY_TRIGGER = "registrar_exam_score_entry_sheet_guard"
_SHEET_FUNCTION = "registrar_guard_exam_score_sheet_integrity"
_ENTRY_FUNCTION = "registrar_guard_exam_score_entry_sheet"

# Mövcud sətirlərdə pozuntu varsa dayan (0041 fəlsəfəsi: heç nə yenidən yazılmır).
_PRECHECK_SQL = f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.{_SHEET_TABLE} AS sheet
          JOIN public.registrar_courseoffering AS offering ON offering.id = sheet.offering_id
         WHERE offering.organization_id <> sheet.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.{_SHEET_TABLE} AS sheet
         WHERE COALESCE(sheet.evidence, '') <> ''
           AND left(sheet.evidence, length('exam_score_sheets/' || sheet.organization_id::text || '/'))
               <> ('exam_score_sheets/' || sheet.organization_id::text || '/')
    ) OR EXISTS (
        SELECT 1
          FROM public.{_ENTRY_TABLE} AS entry
          JOIN public.registrar_enrollment AS enrollment ON enrollment.id = entry.enrollment_id
          LEFT JOIN public.{_SHEET_TABLE} AS sheet ON sheet.id = entry.sheet_id
         WHERE enrollment.organization_id <> entry.organization_id
            OR (
                entry.sheet_id IS NOT NULL
                AND (
                    sheet.organization_id IS DISTINCT FROM entry.organization_id
                    OR sheet.offering_id IS DISTINCT FROM enrollment.offering_id
                )
            )
    ) THEN
        RAISE EXCEPTION 'imtahan bal vərəqi/sətri invariant pozuntusu mövcuddur — 0073 dayandırıldı'
            USING ERRCODE = '23514';
    END IF;
END;
$$;
"""

# ⚠️ plpgsql gövdəsində `%` YOXDUR (nə RAISE format, nə LIKE) və `_apply`
# `params=None` verir — psycopg2 əks halda `%`-i parametr interpolyasiyasına
# salır və miqrasiya (deməli, HƏR test bazasının qurulması) çökür (bax 0067).
# Funksiyalar SECURITY DEFINER-dir və `0041` kimi PUBLIC-dən EXECUTE alınır:
# trigger mexanizmi onları onsuz da icra edir, birbaşa çağırış lazım deyil.
_FORWARD_SQL = f"""
CREATE OR REPLACE FUNCTION public.{_SHEET_FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    evidence_prefix text;
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.offering_id IS DISTINCT FROM OLD.offering_id
    ) THEN
        RAISE EXCEPTION 'imtahan bal vərəqinin kimliyi (təşkilat, açılış) dəyişdirilə bilməz'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM public.registrar_courseoffering AS offering
         WHERE offering.id = NEW.offering_id
           AND offering.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'imtahan bal vərəqinin açılışı eyni təşkilata aid olmalıdır'
            USING ERRCODE = '23514';
    END IF;

    evidence_prefix := 'exam_score_sheets/' || NEW.organization_id::text || '/';
    IF COALESCE(NEW.evidence, '') <> ''
       AND left(NEW.evidence, length(evidence_prefix)) <> evidence_prefix
    THEN
        RAISE EXCEPTION 'imtahan bal vərəqinin skanı öz təşkilat prefiksi altında olmalıdır'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.{_ENTRY_FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    enrollment_organization uuid;
    enrollment_offering uuid;
BEGIN
    SELECT enrollment.organization_id, enrollment.offering_id
      INTO enrollment_organization, enrollment_offering
      FROM public.registrar_enrollment AS enrollment
     WHERE enrollment.id = NEW.enrollment_id;

    IF enrollment_organization IS NULL
       OR enrollment_organization IS DISTINCT FROM NEW.organization_id
    THEN
        RAISE EXCEPTION 'imtahan bal sətrinin qeydiyyatı eyni təşkilata aid olmalıdır'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.sheet_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
          FROM public.{_SHEET_TABLE} AS sheet
         WHERE sheet.id = NEW.sheet_id
           AND sheet.organization_id = NEW.organization_id
           AND sheet.offering_id = enrollment_offering
    ) THEN
        RAISE EXCEPTION 'imtahan bal sətrinin vərəqi eyni təşkilata və qeydiyyatın açılışına aid olmalıdır'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.{_SHEET_FUNCTION}() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.{_ENTRY_FUNCTION}() FROM PUBLIC;

DROP TRIGGER IF EXISTS {_SHEET_TRIGGER} ON public.{_SHEET_TABLE};
CREATE TRIGGER {_SHEET_TRIGGER}
    BEFORE INSERT OR UPDATE OF organization_id, offering_id, evidence ON public.{_SHEET_TABLE}
    FOR EACH ROW EXECUTE FUNCTION public.{_SHEET_FUNCTION}();

DROP TRIGGER IF EXISTS {_ENTRY_TRIGGER} ON public.{_ENTRY_TABLE};
CREATE TRIGGER {_ENTRY_TRIGGER}
    BEFORE INSERT OR UPDATE OF organization_id, enrollment_id, sheet_id ON public.{_ENTRY_TABLE}
    FOR EACH ROW EXECUTE FUNCTION public.{_ENTRY_FUNCTION}();
"""

_REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS {_ENTRY_TRIGGER} ON public.{_ENTRY_TABLE};
DROP TRIGGER IF EXISTS {_SHEET_TRIGGER} ON public.{_SHEET_TABLE};
DROP FUNCTION IF EXISTS public.{_ENTRY_FUNCTION}();
DROP FUNCTION IF EXISTS public.{_SHEET_FUNCTION}();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # FORCE RLS qeyri-superuser cədvəl sahibinə də tətbiq olunur — ön yoxlama
    # BÜTÜN tenantları görməlidir (0041 ilə eyni tranzaksiya-lokal bypass;
    # migrasiya atomikdir, `SET LOCAL` onunla birlikdə bitir).
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'", params=None)
    schema_editor.execute(_PRECHECK_SQL, params=None)
    schema_editor.execute(_FORWARD_SQL, params=None)
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'", params=None)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0072_rls_exam_score_sheet"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
