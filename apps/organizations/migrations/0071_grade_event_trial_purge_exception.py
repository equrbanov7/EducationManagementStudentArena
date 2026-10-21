"""Qiymət reyestrinin append-only qoruyucusuna DAR istisna: sınaq imtahanının tam silinməsi (2026-10-21).

Sahib: «Bu nəticələr test üçün idi … elə bir imtahan keçirilməyib — nə varsa hər yerdə sil.» ``purge_trial_exam``
əmri imtahanı əvvəlcə ``is_deleted`` işarələyir, sonra tranzaksiya daxilində ``SET LOCAL emsarena.trial_exam_purge =
'on'`` qoyub həmin imtahanın cəhdlərinin reyestr sətirlərini silir. Başqa heç bir halda UPDATE/DELETE qadağandır.
"""

from django.db import migrations

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION exams_examgradeevent_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- 2026-10-21 (sahib): sınaq imtahanının tam silinməsi (purge_trial_exam). YALNIZ DELETE, YALNIZ tranzaksiya daxilində
    -- `SET LOCAL emsarena.trial_exam_purge = 'on'` qoyulubsa VƏ cəhdin imtahanı artıq silinmiş (is_deleted) işarələnibsə.
    IF TG_OP = 'DELETE'
       AND current_setting('emsarena.trial_exam_purge', true) = 'on'
       AND EXISTS (
           SELECT 1
           FROM public.exams_examattempt AS attempt
           JOIN public.exams_exam AS exam ON exam.id = attempt.exam_id
           WHERE attempt.id = OLD.attempt_id AND exam.is_deleted
       )
    THEN
        RETURN OLD;
    END IF;

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
"""

_REVERSE_SQL = """
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
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0070_academic_holiday"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
