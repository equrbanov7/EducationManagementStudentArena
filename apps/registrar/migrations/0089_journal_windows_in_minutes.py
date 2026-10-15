"""Jurnal pəncərələri DƏQİQƏ ilə (sahib 2026-10-15: «dəqiqə olaraq settings-ə əlavə et»).

1. Data: «Sistem tənzimləmələri»ndə saxlanmış köhnə saat dəyərləri (``journal.mark_edit_hours`` /
   ``journal.lesson_edit_hours``, 1–72) dəqiqə açarlarına köçürülür (saat × 60) və köhnə sətir silinir —
   sıfırlanmış dəqiqə dəyərinin arxasından köhnə saat dəyəri fallback kimi «dirilməsin». Dəqiqə sətri artıq
   varsa o qalır (yeni açar üstündür). Yararsız köhnə sətrə toxunulmur (kod onu onsuz da tətbiq etmir).
   Geri: dəqiqə dəyəri saata (yuxarı yuvarlaqlaşdırılıb, 1–72) qaytarılır, dəqiqə sətri silinir.
2. Trigger funksiyası (0084-ün eyni qaydası): ``app.journal_unlock='on'`` rəsmi düzəliş yoludur; pəncərə əvvəl
   ``journal.mark_edit_minutes`` (1–4320 dəqiqə), yoxdursa köhnə ``journal.mark_edit_hours`` (1–72 saat × 60),
   o da yoxdursa 120 dəqiqə. Servis qatı (``apps.registrar.journal_edit_windows``) eyni ardıcıllığı izləyir.

⚠️ SQL-də çılpaq faiz işarəsi olmamalıdır (Django mogrify).
"""

import math

from django.db import migrations

_PAIRS = (
    ("journal.mark_edit_hours", "journal.mark_edit_minutes"),
    ("journal.lesson_edit_hours", "journal.lesson_edit_minutes"),
)

_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION registrar_journal_mark_guard() RETURNS trigger AS $$
DECLARE
    window_minutes integer := 120;
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

# 0084-ün funksiyası (geri qaytarma üçün eynilə).
_PREVIOUS_SQL = """
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


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hours_to_minutes(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    for hours_key, minutes_key in _PAIRS:
        old = RuntimeSetting.objects.filter(key=hours_key).first()
        hours = _int(old.value) if old is not None else None
        if old is None or hours is None or not 1 <= hours <= 72:
            continue
        if not RuntimeSetting.objects.filter(key=minutes_key).exists():
            RuntimeSetting.objects.create(key=minutes_key, value=hours * 60, updated_by_id=old.updated_by_id)
        old.delete()


def _minutes_to_hours(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    for hours_key, minutes_key in _PAIRS:
        new = RuntimeSetting.objects.filter(key=minutes_key).first()
        minutes = _int(new.value) if new is not None else None
        if new is None or minutes is None:
            continue
        hours = min(72, max(1, math.ceil(minutes / 60)))
        RuntimeSetting.objects.update_or_create(
            key=hours_key, defaults={"value": hours, "updated_by_id": new.updated_by_id}
        )
        new.delete()


def _apply_function(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FUNCTION_SQL)


def _revert_function(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_PREVIOUS_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0088_journal_hygiene_not_held"),
        ("accounts", "0028_runtimesetting"),
    ]

    operations = [
        migrations.RunPython(_hours_to_minutes, _minutes_to_hours),
        migrations.RunPython(_apply_function, _revert_function),
    ]
