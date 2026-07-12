"""Database backstop: a published exam must retain an active question."""

from django.db import migrations

INSTALL_SQL = r"""
CREATE OR REPLACE FUNCTION emsarena_exam_publish_requires_question()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.is_active IS TRUE
       AND NEW.is_deleted IS FALSE
       AND NOT EXISTS (
           SELECT 1
           FROM exams_examquestion q
           WHERE q.exam_id = NEW.id AND q.is_active IS TRUE
       )
    THEN
        RAISE EXCEPTION 'active exam requires at least one active question'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'active_exam_requires_question';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exams_exam_publish_requires_question ON exams_exam;
CREATE CONSTRAINT TRIGGER exams_exam_publish_requires_question
AFTER INSERT OR UPDATE ON exams_exam
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION emsarena_exam_publish_requires_question();

CREATE OR REPLACE FUNCTION emsarena_preserve_active_exam_question()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_id bigint;
BEGIN
    FOR parent_id IN
        SELECT DISTINCT candidate_id
        FROM unnest(
            CASE
                WHEN TG_OP = 'DELETE' THEN ARRAY[OLD.exam_id]
                ELSE ARRAY[OLD.exam_id, NEW.exam_id]
            END
        ) AS candidate_id
        WHERE candidate_id IS NOT NULL
        ORDER BY candidate_id
    LOOP
        -- Same lock-order root as the application lifecycle service.
        PERFORM id
        FROM exams_exam
        WHERE id = parent_id
        FOR UPDATE;

        IF FOUND
           AND EXISTS (
               SELECT 1
               FROM exams_exam e
               WHERE e.id = parent_id
                 AND e.is_active IS TRUE
                 AND e.is_deleted IS FALSE
           )
           AND NOT EXISTS (
               SELECT 1
               FROM exams_examquestion q
               WHERE q.exam_id = parent_id
                 AND q.is_active IS TRUE
           )
        THEN
            RAISE EXCEPTION 'active exam requires at least one active question'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'active_exam_requires_question';
        END IF;
    END LOOP;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS exams_question_preserve_active_exam ON exams_examquestion;
CREATE TRIGGER exams_question_preserve_active_exam
AFTER DELETE OR UPDATE OF is_active, exam_id ON exams_examquestion
FOR EACH ROW
EXECUTE FUNCTION emsarena_preserve_active_exam_question();
"""


UNINSTALL_SQL = r"""
DROP TRIGGER IF EXISTS exams_question_preserve_active_exam ON exams_examquestion;
DROP FUNCTION IF EXISTS emsarena_preserve_active_exam_question();
DROP TRIGGER IF EXISTS exams_exam_publish_requires_question ON exams_exam;
DROP FUNCTION IF EXISTS emsarena_exam_publish_requires_question();
"""


def install_invariant(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_SQL)


def uninstall_invariant(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(UNINSTALL_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0051_attempt_question_timing"),
    ]

    operations = [
        migrations.RunPython(install_invariant, uninstall_invariant),
    ]
