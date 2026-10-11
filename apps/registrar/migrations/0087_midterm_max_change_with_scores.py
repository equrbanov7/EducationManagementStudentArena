"""Midterm tavanı balı olan komponentdə də dəyişə bilsin — 20 → 30 (sahib 2026-10-10 «Yeni qayda var»).

Sərbəst iş ləğv olundu, onun 10 balı midterm-ə keçdi: «Midterm» komponentinin tavanı RİM «Sistem
tənzimləmələri»ni izləyir (``core.academic_rules.midterm_max``: 30; sərbəst iş açılsa 20). ``0044``-ün
``registrar_guard_component_rubric_evidence`` qoruyucusu isə balı (sübutu) olan komponentin ``max_score``-unu
HƏR HALDA bağlayırdı — cari semestrdə artıq yazılmış midterm balı olan jurnal açılanda tavanın 30-a
qaldırılması ``IntegrityError`` verərdi.

Yeni qayda DAR açılır — ``max_score`` sübutlu komponentdə yalnız bu halda dəyişə bilər:

* komponent aralıq qiymətləndirmədir (``kind = 'kollokvium'`` — Midterm / kollokvium);
* rubriki yoxdur və meyar (rubrik) balı yoxdur — rubrik cəmi ``LEAST(points, max_score)`` tavandan asılıdır;
* yazılmış BÜTÜN ballar yeni tavana sığır (qaldırmaq həmişə; endirmək yalnız ondan böyük bal yoxdursa).

Qalan hər şey əvvəlki kimi bağlıdır: ad / rubrik / açılış / təşkilat dəyişməsi, rubrikli və ya digər növ
komponentin tavanı, sübutlu komponentin silinməsi. Tətbiq tərəfi eyni qaydanı
``interim_components.max_change_allowed`` və ``gradebook_components.save_components``-da yoxlayır.

Qeyri-PostgreSQL backend-lərdə no-op-dur; geri qaytarma ``0044``-ün funksiyasını bayt-bayt bərpa edir.
"""

from django.db import migrations

_FUNCTION_HEAD = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_component_rubric_evidence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
           OR EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id) THEN
            RAISE EXCEPTION 'component rubric evidence is protected' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF (EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
        OR EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id))
       AND (NEW.organization_id IS DISTINCT FROM OLD.organization_id
            OR NEW.offering_id IS DISTINCT FROM OLD.offering_id
            OR NEW.name IS DISTINCT FROM OLD.name
            OR NEW.rubric_id IS DISTINCT FROM OLD.rubric_id
"""

_FUNCTION_TAIL = r"""
        RAISE EXCEPTION 'component rubric evidence is protected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_component_rubric_evidence() FROM PUBLIC;
"""

# Sahib 2026-10-10: rubriksiz aralıq komponentinin tavanı bütün ballar yeni tavana sığırsa dəyişə bilər.
_MAX_SCORE_RELAXED = r"""            OR (NEW.max_score IS DISTINCT FROM OLD.max_score
                AND NOT (
                    NEW.kind = 'kollokvium'
                    AND OLD.rubric_id IS NULL
                    AND NEW.max_score IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
                    AND NOT EXISTS (
                        SELECT 1 FROM public.registrar_componentscore
                         WHERE component_id = OLD.id AND score > NEW.max_score
                    )
                ))) THEN"""

# ``0044``-ün mətni (geri qaytarma üçün).
_MAX_SCORE_0044 = r"""            OR NEW.max_score IS DISTINCT FROM OLD.max_score) THEN"""

RELAXED_SQL = _FUNCTION_HEAD + _MAX_SCORE_RELAXED + _FUNCTION_TAIL
RESTORE_0044_SQL = _FUNCTION_HEAD + _MAX_SCORE_0044 + _FUNCTION_TAIL


def _relax(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(RELAXED_SQL)


def _restore(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(RESTORE_0044_SQL)


class Migration(migrations.Migration):
    dependencies = [("registrar", "0086_journal_hygiene_decision")]

    operations = [migrations.RunPython(_relax, _restore)]
