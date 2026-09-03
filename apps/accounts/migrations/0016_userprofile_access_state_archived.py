"""``UserProfile.AccessState.ARCHIVED`` — məzun/xaric hesab vəziyyəti.

Nə edir:

1. ``access_state`` choices-inə ``archived`` əlavə edir (DB CHECK constraint
   yoxdur — yalnız Django state dəyişir, sütuna toxunulmur).
2. ``accounts_reject_active_staged_profile`` trigger funksiyasını (0013)
   ``CREATE OR REPLACE`` ilə GENİŞLƏNDİRİR: ``staged`` budaqları OLDUĞU KİMİ
   qalır, üzərinə ``archived`` vəziyyətindən ÇIXMAQ üçün eyni
   ``AccountActivationEvidence`` qapısı əlavə olunur.

Niyə lazımdır. Arxiv hesabda ``auth_user.is_active`` QƏSDƏN True-dur (registrar
trigger-ləri tarixi jurnal sətirlərini yalnız o zaman qəbul edir), ona görə
girişi bağlayan yeganə şey ``access_state='archived'``-dir. Qapısız qalsaydı,
istənilən ``UPDATE ... SET access_state='active'`` sətri məzun hesabı bir anda
tam işlək girişə çevirərdi — ``staged`` üçün tələb olunan evidence axını isə
tamamilə yan keçilərdi. İndi hər iki istiqamət eyni qapıdan keçir (fail-closed).

``active → archived`` (arxivləşdirmə) MƏHDUDLAŞDIRICI keçiddir və evidence
tələb ETMİR — ``identity_archive.archive_staged_account`` onu artıq
``activate_staged_account``-un tam qapı dəstindən keçirdikdən SONRA edir.
"""

from django.db import migrations, models

FORWARD_GUARD = """
CREATE OR REPLACE FUNCTION accounts_reject_active_staged_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_id text := COALESCE(
        current_setting('app.account_activation_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.access_state IN ('staged', 'archived')
       AND NEW.access_state <> OLD.access_state THEN
        IF evidence_id = '' OR NOT EXISTS (
            SELECT 1
              FROM public.accounts_accountactivationevidence AS evidence
             WHERE evidence.id::text = evidence_id
               AND evidence.organization_id = NEW.organization_id
               AND evidence.user_ref = NEW.user_id::text
               AND evidence.transaction_id = txid_current()
               AND evidence.consumed_at IS NULL
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'accounts_staged_activation_service_required';
        END IF;
    END IF;
    IF NEW.access_state = 'staged'
       AND EXISTS (
           SELECT 1
           FROM public.auth_user AS account
           WHERE account.id = NEW.user_id
             AND account.is_active
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_staged_user_must_remain_inactive';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reject_active_staged_profile() FROM PUBLIC;
"""

# 0013-dəki orijinal gövdə — geri qaytarma üçün hərfi bərpa.
REVERSE_GUARD = """
CREATE OR REPLACE FUNCTION accounts_reject_active_staged_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_id text := COALESCE(
        current_setting('app.account_activation_evidence_id', true),
        ''
    );
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.access_state = 'staged'
       AND NEW.access_state <> 'staged' THEN
        IF evidence_id = '' OR NOT EXISTS (
            SELECT 1
              FROM public.accounts_accountactivationevidence AS evidence
             WHERE evidence.id::text = evidence_id
               AND evidence.organization_id = NEW.organization_id
               AND evidence.user_ref = NEW.user_id::text
               AND evidence.transaction_id = txid_current()
               AND evidence.consumed_at IS NULL
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'accounts_staged_activation_service_required';
        END IF;
    END IF;
    IF NEW.access_state = 'staged'
       AND EXISTS (
           SELECT 1
           FROM public.auth_user AS account
           WHERE account.id = NEW.user_id
             AND account.is_active
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_staged_user_must_remain_inactive';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reject_active_staged_profile() FROM PUBLIC;
"""


def _apply(sql):
    def _run(_apps, schema_editor):
        # Trigger yalnız PostgreSQL-də mövcuddur (0013 ilə eyni şərt); sqlite
        # lokal/test yolu bu qapını onsuz da daşımır.
        if schema_editor.connection.vendor != "postgresql":
            return
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql)

    return _run


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_rim_user_admin_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="access_state",
            field=models.CharField(
                choices=[
                    ("active", "Aktiv giriş"),
                    ("staged", "Mərhələlənmiş (giriş bağlıdır)"),
                    ("archived", "Arxiv — məzun/xaric (giriş bağlıdır)"),
                ],
                db_index=True,
                default="active",
                help_text="Legacy import staged qalır; məzun/xaric archived olur (giriş bağlı, data qalır).",
                max_length=16,
                verbose_name="Giriş vəziyyəti",
            ),
        ),
        migrations.RunPython(_apply(FORWARD_GUARD), _apply(REVERSE_GUARD)),
    ]
