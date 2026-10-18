"""Müstəqil rəyin düzəlişləri (2026-10-19) — A2 / A4 / A7.

* A2: ``discarded`` statusu (ləğv edilmiş qaralama; nömrəsi yenidən istifadə oluna bilər).
* A4: xatırlatma hadisəsi aid olduğu ``end_date``-i daşıyır; unikal açar ``(contract, kind, threshold, end_date)``.
  ⚠️ 0003-dən ƏVVƏL yazılmış xatırlatma sətirlərində ``end_date`` boşdur (append-only — UPDATE ilə doldurulmur); həmin
  müqavilələr cari hədd üçün bir dəfə yenidən xatırlatma ala bilər (xüsusiyyət hələ prod-da deyil).
* A7: ``organization`` FK-ları PROTECT; hadisədə ``actor_name``; UPDATE trigger-i YALNIZ ``actor_id``-nin NULL-a keçməsinə
  (hesab silinəndə Django ``SET_NULL`` emulyasiyası) icazə verir — registrar 0092 naxışı. DELETE / TRUNCATE qoruyucusu
  (0002) dəyişmir.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "public.hr_contracts_employmentcontractevent"

_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.hr_contracts_event_guard_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
BEGIN
    -- Hesab silinir: Django SET_NULL emulyasiyası yalnız actor_id-ni NULL edir — başqa heç nə dəyişə bilməz.
    IF (to_jsonb(NEW) - 'actor_id') = (to_jsonb(OLD) - 'actor_id')
       AND NEW.actor_id IS NULL AND OLD.actor_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING MESSAGE = 'hr_contracts history is append-only: UPDATE', ERRCODE = '23514';
END;
$function$;
REVOKE ALL ON FUNCTION public.hr_contracts_event_guard_update() FROM PUBLIC;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_GUARD_SQL, params=None)
    schema_editor.execute(f"DROP TRIGGER IF EXISTS hr_contracts_event_append_only_update ON {_TABLE}", params=None)
    schema_editor.execute(
        f"CREATE TRIGGER hr_contracts_event_append_only_update BEFORE UPDATE ON {_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.hr_contracts_event_guard_update()",
        params=None,
    )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS hr_contracts_event_append_only_update ON {_TABLE}", params=None)
    schema_editor.execute(
        f"CREATE TRIGGER hr_contracts_event_append_only_update BEFORE UPDATE ON {_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.hr_contracts_guard_append_only()",
        params=None,
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS public.hr_contracts_event_guard_update()", params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("hr_contracts", "0002_rls_and_guards"),
        ("organizations", "0069_hr_contract_permissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="employmentcontract",
            name="hrc_unique_number_per_org",
        ),
        migrations.RemoveConstraint(
            model_name="employmentcontract",
            name="hrc_status_valid",
        ),
        migrations.RemoveConstraint(
            model_name="employmentcontractevent",
            name="hrc_event_once_per_threshold",
        ),
        migrations.AddField(
            model_name="employmentcontractevent",
            name="actor_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="employmentcontractevent",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="employmentcontract",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employment_contracts",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="employmentcontract",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Qaralama"),
                    ("active", "Qüvvədədir"),
                    ("terminated", "Xitam verilib"),
                    ("renewed", "Yenilənib"),
                    ("discarded", "Ləğv edilib"),
                ],
                default="active",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="employmentcontractevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("created", "Qeydə alındı"),
                    ("edited", "Redaktə olundu"),
                    ("activated", "Qüvvəyə mindi"),
                    ("file_replaced", "Fayl yeniləndi"),
                    ("sent", "İşçiyə göndərildi"),
                    ("acknowledged", "İşçi təsdiqlədi"),
                    ("reminder_sent", "Bitmə xatırlatması göndərildi"),
                    ("expired_notice", "Müddəti bitdi bildirişi göndərildi"),
                    ("terminated", "Xitam verildi"),
                    ("renewed", "Yeni müqavilə ilə yeniləndi"),
                    ("resend_required", "Dəyişdi — yenidən göndərilməlidir"),
                    ("discarded", "Qaralama ləğv edildi"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="employmentcontractevent",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="+", to="organizations.organization"
            ),
        ),
        migrations.AddConstraint(
            model_name="employmentcontract",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    models.Q(("number", ""), _negated=True), models.Q(("status", "discarded"), _negated=True)
                ),
                fields=("organization", "number"),
                name="hrc_unique_number_per_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="employmentcontract",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["draft", "active", "terminated", "renewed", "discarded"])),
                name="hrc_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="employmentcontractevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind__in", ["reminder_sent", "expired_notice"])),
                fields=("contract", "kind", "threshold", "end_date"),
                name="hrc_event_once_per_threshold",
            ),
        ),
        migrations.RunPython(_apply, _revert),
    ]
