"""Fənn birləşdirməsi (2026-10-19) — açılışın ``subject_id``-si üçün DAR, audit-li icazə.

NƏ ÜÇÜN?
--------
``registrar.0045`` açılışın (``registrar_courseoffering``) ``subject_id/period_id/group_id``
sütunlarını jurnal sübutu (qeydiyyat, dərs, qiymət sxemi, cədvəl slotu, komponent, sərbəst iş
mövzusu) olan kimi DONDURUR — bu, tarixçənin başqa fənnə «sürüşməsinin» qarşısını alır.
Dublikat fənlərin birləşdirilməsi isə məhz eyni fənnin İKİ KARTINI birə endirir: açılış öz
dövrü, qrupu və bütün sübutu ilə qalır, yalnız kataloq kartı (eyni fənn) dəyişir. Bu
identiklik düzəlişidir, məzmun dəyişikliyi deyil.

İCAZƏ ŞƏRTLƏRİ (hamısı birlikdə, əks halda köhnə qayda — xəta):
* yalnız ``subject_id`` dəyişir (dövr, qrup, təşkilat EYNİ qalır);
* ``app.registrar_subject_merge_txid`` CARİ tranzaksiyanın id-sidir (``SET LOCAL`` — tranzaksiya
  bitən kimi itir, başqa sorğuya keçmir);
* köhnə fənn ``app.registrar_subject_merge_from`` siyahısında, yeni fənn
  ``app.registrar_subject_merge_to``-dur və hər ikisi açılışla EYNİ təşkilatdadır.
Parametrləri YALNIZ ``apps.registrar.subject_merge_apply`` (və geri qaytarma) qurur; əməl
``core.audit`` jurnalına sətir id-ləri ilə yazılır.

⚠️ MİQRASİYA SIRASI (MƏCBURİ)
----------------------------
``registrar_guard_conditional_parent_identity`` funksiyasını yenidən yazan (``CREATE OR REPLACE``)
İSTƏNİLƏN gələcək registrar miqrasiyası ``dependencies``-ə
``("audit", "0004_registrar_subject_merge_offering_guard")`` əlavə etməli və aşağıdakı
``_MERGE_ALLOWANCE`` blokunu SAXLAMALIDIR. Asılılıq olmasa Django iki miqrasiyanı istənilən sırada
tətbiq edə bilər və bu icazə səssizcə itər. Qoruyucu: ``apps/registrar/tests/test_subject_merge_postgres.py``
(``pytest -m postgres``) canlı funksiyanın mətnində icazəni yoxlayır.

NİYƏ ``audit`` TƏTBİQİNDƏ?
--------------------------
``registrar`` miqrasiya ardıcıllığında 0094 paralel işdə yazılır; ikinci 0094 qrafı qırardı.
Funksiya ``CREATE OR REPLACE`` ilə yenilənir (cədvəl/sütun dəyişmir). Gələcəkdə registrar
miqrasiyası bu funksiyanı yenidən yazarsa, icazəni saxlamalıdır — bunu
``apps/registrar/tests/test_subject_merge_apply.py`` (sübutlu açılışın köçürülməsi) tutur.
"""

from django.db import migrations

_HEADER = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_conditional_parent_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    has_evidence boolean := false;
BEGIN
    IF TG_ARGV[0] = 'course_offering' THEN
        IF NEW.subject_id IS NOT DISTINCT FROM OLD.subject_id
           AND NEW.period_id IS NOT DISTINCT FROM OLD.period_id
           AND NEW.group_id IS NOT DISTINCT FROM OLD.group_id THEN
            RETURN NEW;
        END IF;
"""

_MERGE_ALLOWANCE = r"""
        IF NEW.period_id IS NOT DISTINCT FROM OLD.period_id
           AND NEW.group_id IS NOT DISTINCT FROM OLD.group_id
           AND NEW.organization_id IS NOT DISTINCT FROM OLD.organization_id
           AND COALESCE(current_setting('app.registrar_subject_merge_txid', true), '')
               = pg_current_xact_id()::text
           AND COALESCE(current_setting('app.registrar_subject_merge_to', true), '')
               = NEW.subject_id::text
           AND OLD.subject_id::text = ANY (
               string_to_array(COALESCE(current_setting('app.registrar_subject_merge_from', true), ''), ',')
           )
           AND EXISTS (
               SELECT 1 FROM public.registrar_subject subject
                WHERE subject.id = NEW.subject_id AND subject.organization_id = NEW.organization_id
           )
           AND EXISTS (
               SELECT 1 FROM public.registrar_subject subject
                WHERE subject.id = OLD.subject_id AND subject.organization_id = NEW.organization_id
           ) THEN
            RETURN NEW;
        END IF;
"""

_BODY = r"""
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_enrollment WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_lesson WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_assessmentscheme WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_scheduleslot WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_assessmentcomponent WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_selfworktopic WHERE offering_id = OLD.id);
    ELSIF TG_ARGV[0] = 'assessment_component' THEN
        IF NEW.offering_id IS NOT DISTINCT FROM OLD.offering_id
           AND NEW.rubric_id IS NOT DISTINCT FROM OLD.rubric_id THEN
            RETURN NEW;
        END IF;
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
            OR EXISTS (
                SELECT 1 FROM public.registrar_componentscorecorrection
                 WHERE component_id = OLD.id
            );
    ELSIF TG_ARGV[0] = 'curriculum' THEN
        IF NEW.program_id IS NOT DISTINCT FROM OLD.program_id THEN
            RETURN NEW;
        END IF;
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_curriculumsubject WHERE curriculum_id = OLD.id)
            OR EXISTS (
                SELECT 1 FROM public.registrar_studentacademicrecord
                 WHERE curriculum_id = OLD.id
            );
    ELSE
        RAISE EXCEPTION 'unknown registrar conditional identity guard'
            USING ERRCODE = '23514';
    END IF;

    IF has_evidence THEN
        RAISE EXCEPTION 'registrar parent identity has dependent evidence'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
"""

FORWARD_SQL = _HEADER + _MERGE_ALLOWANCE + _BODY
#: ``registrar.0045``-in orijinal mətni (icazəsiz) — geri qaytarma üçün.
REVERSE_SQL = _HEADER + _BODY


def _forward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARD_SQL)


def _reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0003_rls_auditlog"),
        ("registrar", "0093_retake_window_fees_closure"),
    ]

    operations = [migrations.RunPython(_forward, _reverse)]
