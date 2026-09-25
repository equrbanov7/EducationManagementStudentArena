"""Göndəriş cədvəlləri üçün DB qoruyucuları (servis qatının İKİNCİ qatı).

1. ``subject_folder_submissionevent`` — ƏLAVƏ-ONLY: UPDATE bloklanır (tarixçə
   sonradan «başqa cür» göstərilə bilməz). DELETE QƏSDƏN bloklanmır — təşkilat
   silinəndə CASCADE yolu qırılmasın (``exams.0065`` ilə eyni qərar); göndərişin
   özü PROTECT-dir, adi axında hadisə silinmir.
2. Sərbəst iş CƏMİ ≤ 10 — qəbul edilmiş (``accepted``) sərbəst iş ballarının
   qeydiyyat üzrə cəmi. Servis advisory kilidlə yoxlayır; trigger isə servisdən
   KƏNAR yazını (bulk UPDATE, əl ilə SQL) tutur — öz advisory kilidi ilə, ona görə
   paralel kənar yazılar da cəmi keçə bilməz. Sabit
   ``apps.subject_folder.constants.SELFWORK_TOTAL_CAP`` ilə eynidir (testlə kilidli).

⚠️ ``params=None`` MƏCBURİDİR: plpgsql gövdəsindəki ``%`` psycopg-nin parametr
interpolyasiyasına düşməsin (registrar/0067, exams/0065 ilə eyni tələ).
"""

from django.db import migrations

_EVENTS = "subject_folder_submissionevent"
_SUBMISSIONS = "subject_folder_submission"

_FORWARD_SQL = f"""
CREATE OR REPLACE FUNCTION subject_folder_event_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '{_EVENTS} append-only: % qadagandir', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS subject_folder_event_no_update ON {_EVENTS};
CREATE TRIGGER subject_folder_event_no_update
    BEFORE UPDATE ON {_EVENTS}
    FOR EACH ROW EXECUTE FUNCTION subject_folder_event_append_only();

CREATE OR REPLACE FUNCTION subject_folder_guard_selfwork_total()
RETURNS trigger AS $$
DECLARE
    awarded numeric;
BEGIN
    IF NEW.status = 'accepted' AND NEW.kind = 'selfwork' THEN
        -- Paralel yazıçılar eyni qeydiyyat üzrə serializasiya olunur: READ COMMITTED-də
        -- kilidsiz iki tranzaksiya bir-birinin commit olunmamış balını görməzdi.
        PERFORM pg_advisory_xact_lock(hashtextextended('subject_folder:selfwork_total:' || NEW.enrollment_id::text, 0));
        SELECT COALESCE(SUM(points), 0) INTO awarded
          FROM {_SUBMISSIONS}
         WHERE enrollment_id = NEW.enrollment_id
           AND kind = 'selfwork'
           AND status = 'accepted'
           AND id <> NEW.id;
        IF awarded + COALESCE(NEW.points, 0) > 10 THEN
            RAISE EXCEPTION 'subject_folder: serbest is cemi 10-u kecir (enrollment %)', NEW.enrollment_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS subject_folder_selfwork_total ON {_SUBMISSIONS};
CREATE TRIGGER subject_folder_selfwork_total
    BEFORE INSERT OR UPDATE ON {_SUBMISSIONS}
    FOR EACH ROW EXECUTE FUNCTION subject_folder_guard_selfwork_total();
"""

_REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS subject_folder_selfwork_total ON {_SUBMISSIONS};
DROP FUNCTION IF EXISTS subject_folder_guard_selfwork_total();
DROP TRIGGER IF EXISTS subject_folder_event_no_update ON {_EVENTS};
DROP FUNCTION IF EXISTS subject_folder_event_append_only();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL, params=None)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("subject_folder", "0002_rls_subject_folder"),
    ]

    operations = [migrations.RunPython(_apply, _revert)]
