"""25% — «Ödənişin qaytarılması qərarı» (sahib 2026-10-19, tövsiyə olunan variant).

Defolt qaytarılma YOXDUR; ödənişdən sonra bağlanmış (``rejected`` / ``no_show`` / ``withdrawn``) müraciətə RƏSMİ QƏRARLA
qaytarılma verilə bilər, Mühasibatlıq icranı «Qaytarıldı» ilə qeyd edir (``apps/registrar/retake_refund.py``).

* ``RetakeApplication`` — ``refund_*`` sahələri (vəziyyət, məbləğ, səbəb, əmr № / tarix / sənəd, kim / nə vaxt; icra
  tarixi, arayış №, kim / nə vaxt) + vəziyyətin ardıcıllıq CHECK-i (``registrar_retake_refund_state_consistent``).
* ``registrar_guard_retake_refund`` trigger-i (BEFORE UPDATE): vəziyyət yalnız irəli gedir («» → decided → refunded);
  qərar YALNIZ ödənişi təsdiqlənmiş və ödənişdən sonra bağlanmış 25% müraciətinə verilir; qərar sahələri və status
  qərardan sonra, icra sahələri «qaytarıldı»dan sonra DƏYİŞMİR (istifadəçi silinəndə FK-nın NULL-a düşməsi istisnadır).
  ``refund_restores_attempt`` (defolt true — «Cəhd istifadə olunmuş sayılmasın», sahib qaydası) qərarla donur.
  CHECK (review 2026-10-19, L4): vəziyyət «» ikən HEÇ BİR ``refund_*`` sahəsi dolu deyil; «decided» ikən icra sahələri
  (``refunded_on`` / ``refund_reference`` / ``refunded_at``) boşdur.
  Tarixçə mövcud append-only ``RetakeApplicationEvent`` cədvəlindədir (``refund_decided`` / ``refunded``).
* Yeni cədvəl / cədvəllərarası tenant FK YOXDUR (yalnız istifadəçi FK-ları) — ``registrar_guard_same_org_fk`` trigger
  sayı dəyişmir (``test_integrity_postgres`` 57); RLS ``registrar_retakeapplication``-da artıq var (0091).
Postgres olmayan backend-də RunPython no-op-dur.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.registrar.models.retake
import core.upload_security

_GUARD_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_retake_refund()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF OLD.refund_state = '' AND NEW.refund_state = '' THEN
        RETURN NEW;
    END IF;
    IF NOT (
        (OLD.refund_state = '' AND NEW.refund_state = 'decided')
        OR (OLD.refund_state = 'decided' AND NEW.refund_state IN ('decided', 'refunded'))
        OR (OLD.refund_state = 'refunded' AND NEW.refund_state = 'refunded')
    ) THEN
        RAISE EXCEPTION USING MESSAGE = 'retake refund state only moves forward', ERRCODE = '23514';
    END IF;
    IF OLD.refund_state = '' THEN
        IF NEW.kind <> 'retake_25'
            OR NEW.status NOT IN ('rejected', 'no_show', 'withdrawn')
            OR NEW.payment_verified_at IS NULL THEN
            RAISE EXCEPTION USING MESSAGE = 'retake refund needs an application closed after a verified payment',
                ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status
        OR NEW.refund_amount IS DISTINCT FROM OLD.refund_amount
        OR NEW.refund_reason IS DISTINCT FROM OLD.refund_reason
        OR NEW.refund_order_number IS DISTINCT FROM OLD.refund_order_number
        OR NEW.refund_order_date IS DISTINCT FROM OLD.refund_order_date
        OR NEW.refund_document IS DISTINCT FROM OLD.refund_document
        OR NEW.refund_decided_at IS DISTINCT FROM OLD.refund_decided_at
        OR NEW.refund_restores_attempt IS DISTINCT FROM OLD.refund_restores_attempt
        OR (NEW.refund_decided_by_id IS DISTINCT FROM OLD.refund_decided_by_id AND NEW.refund_decided_by_id IS NOT NULL)
    THEN
        RAISE EXCEPTION USING MESSAGE = 'retake refund decision is immutable', ERRCODE = '23514';
    END IF;
    IF OLD.refund_state = 'refunded' AND (
        NEW.refunded_on IS DISTINCT FROM OLD.refunded_on
        OR NEW.refund_reference IS DISTINCT FROM OLD.refund_reference
        OR NEW.refunded_at IS DISTINCT FROM OLD.refunded_at
        OR (NEW.refunded_by_id IS DISTINCT FROM OLD.refunded_by_id AND NEW.refunded_by_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION USING MESSAGE = 'retake refund execution is immutable', ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.registrar_guard_retake_refund() FROM PUBLIC;
"""


def _apply_security(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_GUARD_FUNCTION)
    schema_editor.execute(
        "CREATE TRIGGER registrar_retake_refund_guard BEFORE UPDATE ON public.registrar_retakeapplication "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_retake_refund()"
    )


def _revert_security(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS registrar_retake_refund_guard ON public.registrar_retakeapplication")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_guard_retake_refund()")


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0093_retake_window_fees_closure"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_decided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_decided_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_document",
            field=models.FileField(
                blank=True,
                max_length=200,
                upload_to=apps.registrar.models.retake.retake_document_path,
                validators=[
                    core.upload_security.FileUploadValidator(
                        allowed_extensions={".jpeg", ".jpg", ".pdf", ".png"}, max_size_mb=10
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_order_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_order_number",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_restores_attempt",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refund_state",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Qaytarılma yoxdur"),
                    ("decided", "Ödənişin qaytarılması qərarı verilib"),
                    ("refunded", "Ödəniş qaytarılıb"),
                ],
                default="",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refunded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refunded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="retakeapplication",
            name="refunded_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="retakeapplicationevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("submitted", "Müraciət göndərildi"),
                    ("receipt_uploaded", "Qəbz yükləndi"),
                    ("payment_verified", "Ödəniş təsdiqləndi"),
                    ("payment_rejected", "Qəbz rədd edildi"),
                    ("admitted", "İmtahana buraxıldı"),
                    ("subgroup_approved", "Alt qrup təsdiqləndi"),
                    ("placed", "Alt qrupa yerləşdirildi"),
                    ("rejected", "Rədd edildi"),
                    ("exam_granted", "İmtahan cəhdi verildi"),
                    ("result_recorded", "Nəticə yazıldı"),
                    ("withdrawn", "Geri götürüldü"),
                    ("no_show", "İmtahana gəlmədi"),
                    ("refund_decided", "Ödənişin qaytarılması qərarı verildi"),
                    ("refunded", "Ödəniş qaytarıldı"),
                ],
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="retakeapplication",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("refund_amount__isnull", True),
                        ("refund_decided_at__isnull", True),
                        ("refund_document", ""),
                        ("refund_order_date__isnull", True),
                        ("refund_order_number", ""),
                        ("refund_reason", ""),
                        ("refund_reference", ""),
                        ("refund_state", ""),
                        ("refunded_at__isnull", True),
                        ("refunded_on__isnull", True),
                    ),
                    models.Q(
                        ("refund_amount__gt", 0),
                        ("refund_decided_at__isnull", False),
                        ("refund_reference", ""),
                        ("refund_state", "decided"),
                        ("refunded_at__isnull", True),
                        ("refunded_on__isnull", True),
                    ),
                    models.Q(
                        ("refund_amount__gt", 0),
                        ("refund_decided_at__isnull", False),
                        ("refund_state", "refunded"),
                        ("refunded_at__isnull", False),
                        ("refunded_on__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="registrar_retake_refund_state_consistent",
            ),
        ),
        migrations.RunPython(_apply_security, _revert_security),
    ]
