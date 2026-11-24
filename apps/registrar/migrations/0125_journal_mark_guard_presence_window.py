"""Xana kilidi trigger-i: balsız i/e xanası öz müddətindən sonra donur (sahib 2026-11-21, RİM rəhbəri).

Sahib: «i/e qoyulandan sonra 1 gün ərzində müəllim onu dəyişə bilsin, sonra q/b kimi donsun … əvvəlki olanlarda
elə donsun … hamısını sistem tənzimləmələrindən idarə edim.» 0106 köhnə dəyəri balsız i/e (``status='present'``,
``score`` boş) olan ``registrar_lessonmark`` sətrinin UPDATE-ini vaxtdan asılı olmadan buraxırdı. İndi YALNIZ o
budaq dəyişir:

* ``journal.presence_lock_enabled`` saxlanıb və YALANDIRSA (``false`` / ``0`` / ``off`` / ``no`` — servisin
  ``coerce`` qaydası) — əvvəlki kimi buraxılır (0106 davranışı);
* yoxsa (sətir yoxdur → defolt yanılı) ``OLD.created_at`` ``journal.presence_edit_minutes``-dan (1–43200; sətir
  yoxdursa 1440 = 1 gün) köhnədirsə UPDATE bloklanır — köçürülmüş (``entered_by`` boş) i/e də; müddət ərzində
  buraxılır (15 dəqiqəlik q/b/bal pəncərəsindən asılı deyil — servis qatı i/e-ni «yeni qeyd» kimi yazır).

Qalan hər şey 0106 ilə EYNİDİR: ``app.journal_unlock='on'`` (RİM rəsmi düzəlişi, data bərpası «tam redaktə»,
sistem yazıları) bütün kilidləri keçir; q/b/bal üçün dəqiqə açarı (1–4320), yoxdursa köhnə saat açarı
(1–72 × 60), o da yoxdursa 15 dəqiqə; kilid ``OLD.created_at``-dan sayılır; ``registrar_componentscore`` (eyni
funksiya) dəyişmir — ``OLD.status`` yalnız ``TG_TABLE_NAME`` yoxlamasının İÇİNDƏ oxunur. Geri qaytarma 0106-nın
gövdəsini bərpa edir.

⚠️ SQL-də çılpaq faiz işarəsi olmamalıdır (Django mogrify).
"""

from django.db import migrations

_FUNCTION_TEMPLATE = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
DECLARE
    window_minutes integer := 15;
__DECLARE__    raw jsonb;
BEGIN
    IF current_setting('app.journal_unlock', true) = 'on' THEN
        RETURN NEW;
    END IF;
__OPEN_PRESENCE__
    SELECT value INTO raw FROM accounts_runtimesetting WHERE key = 'journal.mark_edit_minutes';
    IF raw IS NOT NULL AND jsonb_typeof(raw) = 'number' THEN
        window_minutes := LEAST(GREATEST((raw #>> '{}')::numeric::integer, 1), 4320);
    ELSE
        SELECT value INTO raw FROM accounts_runtimesetting WHERE key = 'journal.mark_edit_hours';
        IF raw IS NOT NULL AND jsonb_typeof(raw) = 'number' THEN
            window_minutes := LEAST(GREATEST((raw #>> '{}')::numeric::integer, 1), 72) * 60;
        END IF;
    END IF;
    IF OLD.created_at < (now() - make_interval(mins => window_minutes)) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'journal mark is frozen (' || window_minutes::text || ' min window elapsed)',
            ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# 0106: balsız i/e (iştirak) xanası — vaxtdan asılı olmadan buraxılır (sahib 2026-10-26).
_OPEN_PRESENCE_0106 = """    IF TG_TABLE_NAME = 'registrar_lessonmark' THEN
        IF OLD.status = 'present' AND OLD.score IS NULL THEN
            RETURN NEW;
        END IF;
    END IF;"""

# 0125: balsız i/e öz müddətində buraxılır, sonra donur; açar söndürülüdə 0106 kimi (sahib 2026-11-21).
_OPEN_PRESENCE_0125 = """    IF TG_TABLE_NAME = 'registrar_lessonmark' THEN
        IF OLD.status = 'present' AND OLD.score IS NULL THEN
            SELECT value INTO raw FROM accounts_runtimesetting WHERE key = 'journal.presence_lock_enabled';
            IF raw IS NOT NULL AND lower(raw #>> '{}') IN ('false', '0', 'off', 'no') THEN
                RETURN NEW;
            END IF;
            SELECT value INTO raw FROM accounts_runtimesetting WHERE key = 'journal.presence_edit_minutes';
            IF raw IS NOT NULL AND jsonb_typeof(raw) = 'number' THEN
                presence_minutes := LEAST(GREATEST((raw #>> '{}')::numeric::integer, 1), 43200);
            END IF;
            IF OLD.created_at < (now() - make_interval(mins => presence_minutes)) THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'journal presence mark is frozen (' || presence_minutes::text || ' min window elapsed)',
                    ERRCODE = 'raise_exception';
            END IF;
            RETURN NEW;
        END IF;
    END IF;"""

_FUNCTION_SQL = _FUNCTION_TEMPLATE.replace("__DECLARE__", "    presence_minutes integer := 1440;\n").replace(
    "__OPEN_PRESENCE__", _OPEN_PRESENCE_0125
)
_PREVIOUS_SQL = _FUNCTION_TEMPLATE.replace("__DECLARE__", "").replace("__OPEN_PRESENCE__", _OPEN_PRESENCE_0106)


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FUNCTION_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_PREVIOUS_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0124_lesson_is_passive"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
