"""«İmtahan şansı» append-only qoruyucusuna DAR istisna: sınaq imtahanının tam silinməsi (2026-10-24).

Sahib («JS Loop»): «sınaq məqsədi ilə yaradılmışdı … bununla bağlı nə varsa hər yerdən sil». ``purge_trial_exam``
imtahanı əvvəlcə ``is_deleted`` işarələyir, sonra tranzaksiya daxilində ``SET LOCAL emsarena.trial_exam_purge =
'on'`` qoyub həmin imtahanın MÜRACİƏTƏ BAĞLI OLMAYAN ``registrar_examchancegrant`` sətirlərini silir (organizations
0071 naxışı). Digər cədvəllər (müraciət hadisələri, qəbzlər), UPDATE və başqa hər hal əvvəlki kimi qadağandır.
"""

from django.db import migrations

_BODY_HEAD = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_retake_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    has_rows boolean;
BEGIN
"""

#: İç-içə IF: PL/pgSQL ``AND``-i qısa-qapanmaya zəmanət vermir, digər cədvəllərin ``OLD``-unda ``exam_id`` yoxdur.
_PURGE_EXCEPTION = r"""
    IF TG_OP = 'DELETE' AND TG_TABLE_NAME = 'registrar_examchancegrant' THEN
        IF current_setting('emsarena.trial_exam_purge', true) = 'on'
           AND OLD.application_id IS NULL
           AND EXISTS (SELECT 1 FROM public.exams_exam AS exam WHERE exam.id = OLD.exam_id AND exam.is_deleted)
        THEN
            RETURN OLD;
        END IF;
    END IF;
"""

_BODY_TAIL = r"""
    IF TG_OP = 'TRUNCATE' THEN
        IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
            RETURN NULL;
        END IF;
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM ' || quote_ident(TG_TABLE_SCHEMA) || '.'
            || quote_ident(TG_TABLE_NAME) || ')' INTO has_rows;
        IF NOT has_rows THEN
            RETURN NULL;
        END IF;
    END IF;
    RAISE EXCEPTION USING MESSAGE = 'registrar retake history is append-only: ' || TG_OP, ERRCODE = '23514';
END;
$function$;
REVOKE ALL ON FUNCTION public.registrar_guard_retake_append_only() FROM PUBLIC;
"""

_FORWARD_SQL = _BODY_HEAD + _PURGE_EXCEPTION + _BODY_TAIL
_REVERSE_SQL = _BODY_HEAD + _BODY_TAIL


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0096_exam_chance_document"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
