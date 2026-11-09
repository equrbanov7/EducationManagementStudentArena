"""Sahib 2026-11-09: eyni FİN-li bağlı hesab — işçi hesabı bağlı tələbə hesabının jurnalına da bal yaza bilməz.

0119 trigger-i yalnız ``own.student_id = NEW.entered_by_id`` (eyni hesab) yoxlayırdı. İndi müəllifin işçi profilinin
``fin_shared_with_id`` (bağlı tələbə hesabı, ``apps/accounts/shared_fin.py``) də «özü» sayılır. Geri: 0119 funksiyası.
"""

import importlib

from django.db import migrations

_PREV = importlib.import_module("apps.registrar.migrations.0119_self_conflict_author_guard")
FUNCTION = _PREV.FUNCTION
TABLES = _PREV.TABLES

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
           AND own.offering_id = target_offering
           AND (
               own.student_id = NEW.entered_by_id
               OR own.student_id IN (
                   SELECT profile.fin_shared_with_id
                     FROM public.accounts_userprofile profile
                    WHERE profile.user_id = NEW.entered_by_id
                      AND profile.fin_shared_with_id IS NOT NULL
               )
           )
    ) THEN
        RAISE EXCEPTION 'registrar score author is a student of this offering (self-conflict)'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.{FUNCTION}() FROM PUBLIC;
"""


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FUNCTION_SQL)  # trigger-lər 0119-dan qalır, yalnız funksiya əvəzlənir


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_PREV._FUNCTION_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0120_lesson_topic_textfield"),
        ("accounts", "0036_shared_fin_linked_accounts_2026_11_09"),
    ]

    operations = [migrations.RunPython(_install, _revert)]
