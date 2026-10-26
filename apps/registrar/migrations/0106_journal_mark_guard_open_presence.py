"""Xana kilidi trigger-i: balsız i/e xanası pəncərədən sonra da dəyişir (sahib 2026-10-26).

Sahib: «E-jurnalda 15 dəqiqə sonra i/e-ni dəyişmək olmur — onu dəyişmək olsun; qb-ni və balı dəyişmək olmasın.»
Servis qatı (``journal_edit_windows.mark_lock_reason``) kilidi yalnız q/b və bal daşıyan xanaya qoyur; trigger də
eyni istisnanı edir: ``registrar_lessonmark``-da KÖHNƏ dəyəri balsız i/e (``status='present'``, ``score`` boş)
olan sətrin UPDATE-i pəncərədən asılı deyil. Yazma pəncərəsi (7 gün, aktivləşdirmə) yalnız servis qatındadır —
boş xananın INSERT-i kimi. Qalan qayda 0100 ilə eynidir: ``app.journal_unlock='on'`` rəsmi yol; dəqiqə açarı
(1–4320), yoxdursa köhnə saat açarı (1–72 × 60), o da yoxdursa 15 dəqiqə; kilid ``OLD.created_at``-dan sayılır.
``registrar_componentscore`` (eyni funksiya, 0024) dəyişmir — orada i/e yoxdur; ``OLD.status`` yalnız
``TG_TABLE_NAME`` yoxlamasının İÇİNDƏ oxunur (componentscore sətrində o sahə yoxdur).

⚠️ SQL-də çılpaq faiz işarəsi olmamalıdır (Django mogrify).
"""

from django.db import migrations

_FUNCTION_TEMPLATE = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
DECLARE
    window_minutes integer := 15;
    raw jsonb;
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

# Balsız i/e (iştirak) xanası — kilid yalnız q/b və bala düşür (sahib 2026-10-26).
_OPEN_PRESENCE_SQL = """    IF TG_TABLE_NAME = 'registrar_lessonmark' THEN
        IF OLD.status = 'present' AND OLD.score IS NULL THEN
            RETURN NEW;
        END IF;
    END IF;"""

_FUNCTION_SQL = _FUNCTION_TEMPLATE.replace("__OPEN_PRESENCE__", _OPEN_PRESENCE_SQL)
_PREVIOUS_SQL = _FUNCTION_TEMPLATE.replace("__OPEN_PRESENCE__\n", "")  # 0100


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FUNCTION_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_PREVIOUS_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0105_journal_share"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
