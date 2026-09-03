"""``exams_questionsubmissionevent`` — ƏLAVƏ-ONLY (UPDATE bloklanır).

Audit 2026-09-03 (Wave 2, P1): model docstring-i lenti «əlavə-only» elan edir
(«Sətirlər YALNIZ əlavə olunur — redaktə/silmə YOXDUR»), lakin qayda YALNIZ
servis qatının nizamı idi: nə DB trigger-i, nə də model qapısı vardı.
``registrar.StudentMovement`` (0067) və ``workload.LoadObjection`` (0005) üçün
trigger var — bu lent isə kafedra → imtahan mərkəzi zəncirinin YEGANƏ sətir-
sətir izidir və eyni müdafiəni almalıdır.

⚠️ DELETE QƏSDƏN BLOKLANMIR: ``submission`` FK-si ``CASCADE``-dır və
``views/teacher/submission_inbox.py`` göndərişin özünü silə bilir — blanket
DELETE trigger-i həmin qanuni axını qırardı. Tamperinq vektoru UPDATE-dir
(«qərarı sonradan başqa cür göstərmək»), o bağlanır. Göndərişin bütövlükdə
silinməsi ayrıca ``core.audit`` sətri qoyur.
"""

from django.db import migrations

_TABLE = "exams_questionsubmissionevent"

# ⚠️ `params=None` MƏCBURİDİR: plpgsql gövdəsindəki `%` psycopg-nin parametr
# interpolyasiyasına düşməsin (registrar/0067 ilə eyni tələ).
_FORWARD_SQL = f"""
CREATE OR REPLACE FUNCTION emsarena_question_submission_event_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '{_TABLE} append-only: % qadagandir', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS question_submission_event_no_update ON {_TABLE};
CREATE TRIGGER question_submission_event_no_update
    BEFORE UPDATE ON {_TABLE}
    FOR EACH ROW EXECUTE FUNCTION emsarena_question_submission_event_append_only();
"""

_REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS question_submission_event_no_update ON {_TABLE};
DROP FUNCTION IF EXISTS emsarena_question_submission_event_append_only();
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
        ("exams", "0064_question_submission_chair_backfill"),
        ("organizations", "0037_rls_question_submission_event"),
    ]

    operations = [migrations.RunPython(_apply, _revert)]
