"""Make the manual grade ledger physically append-only in PostgreSQL."""

from django.db import migrations

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION exams_examgradeevent_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.id IS NOT DISTINCT FROM NEW.id
       AND OLD.attempt_id IS NOT DISTINCT FROM NEW.attempt_id
       AND OLD.old_score IS NOT DISTINCT FROM NEW.old_score
       AND OLD.new_score IS NOT DISTINCT FROM NEW.new_score
       AND OLD.max_points IS NOT DISTINCT FROM NEW.max_points
       AND OLD.created_at IS NOT DISTINCT FROM NEW.created_at
       AND (
           OLD.question_id IS NOT DISTINCT FROM NEW.question_id
           OR (OLD.question_id IS NOT NULL AND NEW.question_id IS NULL)
       )
       AND (
           OLD.grader_id IS NOT DISTINCT FROM NEW.grader_id
           OR (OLD.grader_id IS NOT NULL AND NEW.grader_id IS NULL)
       )
       AND (
           OLD.question_id IS DISTINCT FROM NEW.question_id
           OR OLD.grader_id IS DISTINCT FROM NEW.grader_id
       )
    THEN
        -- Preserve the ledger row when a referenced question/user is removed
        -- through its declared ON DELETE SET NULL foreign key.
        RETURN NEW;
    END IF;

    RAISE EXCEPTION USING MESSAGE =
        'exams_examgradeevent append-only: ' || TG_OP || ' qadağandır';
END;
$$;

DROP TRIGGER IF EXISTS exams_examgradeevent_append_only ON exams_examgradeevent;
CREATE TRIGGER exams_examgradeevent_append_only
BEFORE UPDATE OR DELETE ON exams_examgradeevent
FOR EACH ROW
EXECUTE FUNCTION exams_examgradeevent_append_only_guard();

CREATE OR REPLACE FUNCTION exams_examgradeevent_insert_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.question_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM public.exams_examattempt AS attempt
        JOIN public.exams_examquestion AS question
          ON question.exam_id = attempt.exam_id
        WHERE attempt.id = NEW.attempt_id
          AND question.id = NEW.question_id
    ) THEN
        RAISE EXCEPTION
            'exams_examgradeevent: question attempt-in imtahanına aid deyil';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exams_examgradeevent_insert_integrity ON exams_examgradeevent;
CREATE TRIGGER exams_examgradeevent_insert_integrity
BEFORE INSERT ON exams_examgradeevent
FOR EACH ROW
EXECUTE FUNCTION exams_examgradeevent_insert_integrity_guard();
"""

_REVERSE_SQL = """
DROP TRIGGER IF EXISTS exams_examgradeevent_insert_integrity ON exams_examgradeevent;
DROP FUNCTION IF EXISTS exams_examgradeevent_insert_integrity_guard();
DROP TRIGGER IF EXISTS exams_examgradeevent_append_only ON exams_examgradeevent;
DROP FUNCTION IF EXISTS exams_examgradeevent_append_only_guard();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0022_rls_grade_event"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
