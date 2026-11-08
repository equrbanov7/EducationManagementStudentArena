"""Tələbə + heyət rolu: öz jurnalına bal yazmaq DB səviyyəsində də qadağandır (sahib qaydası 2026-11-08).

Tətbiq qatı (``organizations.self_conflict`` → ``journal_access``, ``gradebook.save_marks``, imtahan balı) qarışıq
istifadəçini onsuz da dayandırır; bu trigger son müdafiə xəttidir: qiymət sətrinin müəllifi (``entered_by``) HƏMİN
açılışa yazılmış tələbədirsə yazı rədd olunur (``23514``).

* INSERT həmişə yoxlanır. UPDATE yalnız ``entered_by_id`` və ya ``enrollment_id`` DƏYƏRİ dəyişəndə yoxlanır —
  birləşmə / köçürmə alətləri (``student_merge``, ``twin_merge_scored``, ``twin_relocate``) sütunu eyni müəlliflə
  yenidən yazanda köhnə sətir rədd olunmur. Miqrasiya mövcud sətirləri skan etmir və düzəltmir.
* Axtarış Enrollment-in unikal (organization, student, offering) indeksindən gedir.
* Qeyri-PostgreSQL backend-də no-op.

Deploy-dan ƏVVƏL mövcud pozuntuları saymaq (yalnız oxu)::

    python manage.py count_self_conflict_marks

və ya birbaşa SQL — :data:`VIOLATION_COUNT_SQL` (hər cədvəl üçün bir sətir: cədvəl adı, say).
"""

from django.db import migrations

FUNCTION = "registrar_guard_author_not_enrolled"

#: ``entered_by`` + ``enrollment`` daşıyan jurnal/qiymət cədvəlləri.
TABLES = (
    "registrar_lessonmark",
    "registrar_componentscore",
    "registrar_criterionscore",
    "registrar_coursework",
    "registrar_finalgrade",
    "registrar_examscoreentry",
)
_TRIGGER = "registrar_author_not_enrolled_guard"

_FUNCTION_SQL = rf"""
CREATE OR REPLACE FUNCTION public.{FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    target_offering uuid;
BEGIN
    IF NEW.entered_by_id IS NULL OR NEW.enrollment_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.entered_by_id IS NOT DISTINCT FROM NEW.entered_by_id
       AND OLD.enrollment_id IS NOT DISTINCT FROM NEW.enrollment_id THEN
        RETURN NEW;
    END IF;
    SELECT enrollment.offering_id
      INTO target_offering
      FROM public.registrar_enrollment enrollment
     WHERE enrollment.id = NEW.enrollment_id;
    IF target_offering IS NOT NULL AND EXISTS (
        SELECT 1
          FROM public.registrar_enrollment own
         WHERE own.organization_id = NEW.organization_id
           AND own.student_id = NEW.entered_by_id
           AND own.offering_id = target_offering
    ) THEN
        RAISE EXCEPTION 'registrar score author is a student of this offering (self-conflict)'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.{FUNCTION}() FROM PUBLIC;
"""

#: Mövcud pozuntuların sayı (yalnız oxu) — deploy-dan əvvəl prod yoxlaması üçün.
VIOLATION_COUNT_SQL = "\nUNION ALL\n".join(
    f"""SELECT '{table}' AS table_name, COUNT(*) AS violations
  FROM public.{table} mark
  JOIN public.registrar_enrollment target ON target.id = mark.enrollment_id
 WHERE mark.entered_by_id IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM public.registrar_enrollment own
        WHERE own.organization_id = mark.organization_id
          AND own.student_id = mark.entered_by_id
          AND own.offering_id = target.offering_id
   )"""
    for table in TABLES
)


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FUNCTION_SQL)
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {_TRIGGER} BEFORE INSERT OR UPDATE OF entered_by_id, enrollment_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{FUNCTION}()"
        )


def _remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{table}")
    schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{FUNCTION}()")


class Migration(migrations.Migration):
    dependencies = [("registrar", "0118_seminar_groups")]

    operations = [migrations.RunPython(_install, _remove)]
