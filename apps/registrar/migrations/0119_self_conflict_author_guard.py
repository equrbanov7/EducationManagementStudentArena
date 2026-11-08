"""Tələbə + heyət rolu: öz jurnalına bal yazmaq DB səviyyəsində də qadağandır (sahib qaydası 2026-11-08).

Tətbiq qatı (``organizations.self_conflict`` → ``gradebook.save_marks``, ``journal_access``, imtahan balı) qarışıq
istifadəçini onsuz da dayandırır; bu trigger son müdafiə xəttidir: qiymət sətrinin müəllifi (``entered_by``) HƏMİN
açılışa yazılmış tələbədirsə yazı rədd olunur (``23514``).

* Yalnız INSERT və ``entered_by_id`` / ``enrollment_id`` dəyişən UPDATE yoxlanır — mövcud sətirlər yenidən yazılmır,
  köhnə data toxunulmur (miqrasiya heç nəyi skan etmir və düzəltmir).
* Axtarış Enrollment-in unikal (organization, student, offering) indeksindən gedir.
* Qeyri-PostgreSQL backend-də no-op.
"""

from django.db import migrations

_FUNCTION = "registrar_guard_author_not_enrolled"

_FUNCTION_SQL = rf"""
CREATE OR REPLACE FUNCTION public.{_FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    author bigint;
    target_offering uuid;
BEGIN
    author := NULLIF(to_jsonb(NEW) ->> 'entered_by_id', '')::bigint;
    IF author IS NULL OR NEW.enrollment_id IS NULL THEN
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
           AND own.student_id = author
           AND own.offering_id = target_offering
    ) THEN
        RAISE EXCEPTION 'registrar score author is a student of this offering (self-conflict)'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
"""

#: ``entered_by`` + ``enrollment`` daşıyan jurnal/qiymət cədvəlləri.
_TABLES = (
    "registrar_lessonmark",
    "registrar_componentscore",
    "registrar_criterionscore",
    "registrar_coursework",
    "registrar_finalgrade",
    "registrar_examscoreentry",
)
_TRIGGER = "registrar_author_not_enrolled_guard"


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FUNCTION_SQL)
    for table in _TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {_TRIGGER} BEFORE INSERT OR UPDATE OF entered_by_id, enrollment_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{_FUNCTION}()"
        )


def _remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(_TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON public.{table}")
    schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{_FUNCTION}()")


class Migration(migrations.Migration):
    dependencies = [("registrar", "0118_seminar_groups")]

    operations = [migrations.RunPython(_install, _remove)]
