"""Xana kilidinin DB defoltu 15 dəqiqə (sahib 2026-10-25).

Sahib: «müəllim kiməsə q/b və ya bal yazıbsa, yazdığından 15 dəqiqə sonra onu geri dəyişə bilməsin, olduğu kimi
qalsın.» Servis qatının defoltu (``journal.mark_edit_minutes`` → 15, ``core.runtime_settings``) ilə trigger-in
defoltu üst-üstə düşməlidir: «Sistem tənzimləmələri»ndə sətir YOXDURSA trigger də 15 dəqiqə tətbiq edir. Qalan
qayda 0089 ilə eynidir: ``app.journal_unlock='on'`` rəsmi yol (sənədli düzəliş, midterm/imtahan sinxronu);
dəqiqə açarı (1–4320), yoxdursa köhnə saat açarı (1–72 × 60). Kilid İLK yazılışdan (``created_at``) sayılır.
Trigger həm ``registrar_lessonmark``, həm ``registrar_componentscore`` üzərindədir (0024) — servis qatı da hər
ikisində eyni açarı oxuyur (``mark_edit_window``).

⚠️ SQL-də çılpaq faiz işarəsi olmamalıdır (Django mogrify).
"""

from django.db import migrations

_FUNCTION_TEMPLATE = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
DECLARE
    window_minutes integer := __DEFAULT__;
    raw jsonb;
BEGIN
    IF current_setting('app.journal_unlock', true) = 'on' THEN
        RETURN NEW;
    END IF;
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

_FUNCTION_SQL = _FUNCTION_TEMPLATE.replace("__DEFAULT__", "15")
_PREVIOUS_SQL = _FUNCTION_TEMPLATE.replace("__DEFAULT__", "120")  # 0089


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FUNCTION_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_PREVIOUS_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0099_external_credit_recognition"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
