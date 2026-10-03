"""Jurnal qeydinin donma müddəti (q/b, i/e, bal) «Sistem tənzimləmələri»ndən oxunur (sahib 2026-10-03).

0024 trigger-i ``interval '2 hours'`` sabit yazırdı — RİM rəhbəri müddəti artırsa da DB dəyişikliyi rədd edərdi.
İndi funksiya ``accounts_runtimesetting`` cədvəlindən ``journal.mark_edit_hours`` açarını oxuyur (1–72 saat;
yoxdursa / yararsızdırsa 2 saat). Qalan qayda eynidir: ``app.journal_unlock='on'`` rəsmi düzəliş yolu.
"""

from django.db import migrations

_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
DECLARE
    window_hours integer := 2;
    raw jsonb;
BEGIN
    IF current_setting('app.journal_unlock', true) = 'on' THEN
        RETURN NEW;
    END IF;
    SELECT value INTO raw FROM accounts_runtimesetting WHERE key = 'journal.mark_edit_hours';
    IF raw IS NOT NULL AND jsonb_typeof(raw) = 'number' THEN
        window_hours := LEAST(GREATEST((raw #>> '{}')::numeric::integer, 1), 72);
    END IF;
    IF OLD.created_at < (now() - make_interval(hours => window_hours)) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'journal mark is frozen (' || window_hours::text || 'h window elapsed)',
            ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_PREVIOUS_SQL = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
BEGIN
    IF current_setting('app.journal_unlock', true) = 'on' THEN
        RETURN NEW;
    END IF;
    IF OLD.created_at < (now() - interval '2 hours') THEN
        RAISE EXCEPTION 'journal mark is frozen (2h window elapsed)'
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FUNCTION_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_PREVIOUS_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0083_enrollment_status_suspended"),
        ("accounts", "0028_runtimesetting"),
    ]

    operations = [migrations.RunPython(_apply, _revert)]
