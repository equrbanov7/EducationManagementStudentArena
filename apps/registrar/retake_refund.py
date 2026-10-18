"""25% — «Ödənişin qaytarılması qərarı» və icrası (sahib 2026-10-19, tövsiyə olunan variant).

QAYDA: defolt qaytarılma YOXDUR (``retake_closure`` bağlanışı «Qaytarılma yoxdur» yazır). Qaytarılma YALNIZ rəsmi
qərarla verilir və yalnız ÖDƏNİŞİ TƏSDİQLƏNMİŞ, sonra bağlanmış (``rejected`` / ``no_show`` / ``withdrawn``) 25%
müraciətinə, BİR DƏFƏ.

* **Qərar** — :func:`decide`. Kim: ``retake.manage`` TƏŞKİLAT əhatəsində (Tədris şöbəsi / RİM; superadmin / sahib).
  Dekan ``retake.manage``-i fakültə (UNIT) əhatəsində daşıyır — pul qaytarılması təşkilat səviyyəli maliyyə qərarıdır,
  ona görə dekan VERƏ BİLMƏZ (HTTP 403; ``has_org_wide_key`` — təhsil haqqı cədvəli / pəncərə ilə eyni qayda).
  Tələb: əmr № + tarix VƏ YA qərar sənədi (``retake_closure.clean_decision`` — bağlanışla eyni yoxlama) və səbəb
  ≥ 20 simvol (``retake_rules.clean_reason``). Məbləğ — defolt ödənilmiş məbləğ (``paid_amount``); qismən qaytarılma
  üçün daha az yazıla bilər (0 < məbləğ ≤ ödənilən). Ödənilən məbləğ qeyd olunmayıbsa (köhnə təsdiq) məbləğ məcburidir.
  CƏHD (review 2026-10-19, sahib qaydası — tövsiyə olunan variant): qaytarılma universitetin ödənilmiş cəhdin
  verilmədiyini tanımasıdır, ona görə DEFOLT olaraq cəhd istifadə olunmuş SAYILMIR («Cəhd istifadə olunmuş sayılmasın»,
  ``refund_restores_attempt``); qərarı verən bunu söndürə bilər. Bayraq qərarla birlikdə donur.
* **İcra** — :func:`mark_refunded`. Kim: ``retake.payment_verify`` (Mühasibatlıq), müraciət əhatəsində. Tələb:
  qaytarılma tarixi (qərardan əvvəl və gələcəkdə ola bilməz) + bank arayışı / ödəniş tapşırığı №.

Hər addım: müraciət ``select_for_update`` ilə kilidlənir, səlahiyyət YAZIDAN ƏVVƏL yoxlanır, ``refund_*`` sahələri
yazılır (DB trigger-i ``registrar_guard_retake_refund`` onları bir dəfəlik edir), append-only ``RetakeApplicationEvent``
(``refund_decided`` / ``refunded``) + ``core.audit.log_action``; bildiriş commit-dən SONRA və xətaya dözümlü
(``retake_notify.notify_refund``). Sistem PUL KÖÇÜRMÜR — bu yalnız qeyddir.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from . import retake_access, retake_closure, retake_fees, retake_files, retake_notify, retake_rules
from .models import RetakeActorRole, RetakeEventAction, RetakeKind, RetakeRefundState, RetakeStatus
from .retake_services import lock, record_event

_CTX = "registrar.retake"

#: Qaytarılma qərarı verilə bilən (ödənişdən sonra bağlanmış) statuslar.
REFUNDABLE_STATUSES = frozenset({RetakeStatus.REJECTED, RetakeStatus.NO_SHOW, RetakeStatus.WITHDRAWN})
REFERENCE_MAX = 120


def can_decide(user, organization) -> bool:
    """Qərar — ``retake.manage`` TƏŞKİLAT əhatəsində (dekanın UNIT əhatəsi kifayət deyil)."""
    return retake_access.has_org_wide_key(user, organization, retake_rules.PERM_MANAGE)


def can_mark(user, organization) -> bool:
    return retake_access.has_key(user, organization, retake_rules.PERM_PAYMENT_VERIFY)


def is_refundable(application) -> bool:
    """Ödənişi təsdiqlənmiş, sonra bağlanmış 25% müraciəti və hələ qərar verilməyib."""
    return (
        application.kind == RetakeKind.RETAKE_25
        and application.status in REFUNDABLE_STATUSES
        and application.payment_verified_at is not None
        and not application.refund_state
    )


def _clean_amount(raw, paid):
    amount = retake_fees.clean_amount(raw, required=paid is None, positive=True)
    if amount is None:
        return paid
    if paid is not None and amount > paid:
        raise ValidationError(pgettext(_CTX, "Qaytarılacaq məbləğ ödənilən məbləğdən çox ola bilməz."))
    return amount


def _metadata_money(value):
    return str(value) if value is not None else None


@transaction.atomic
def decide(
    *,
    actor,
    organization,
    application_id,
    reason,
    amount=None,
    order_number="",
    order_date=None,
    document=None,
    restores_attempt=True,
    request=None,
):
    """«Ödənişin qaytarılması qərarı» — bir dəfə, yalnız ödənişdən sonra bağlanmış müraciətə.

    ``restores_attempt`` (defolt ``True``, sahib qaydası): qaytarılma ödənilmiş cəhdin verilmədiyini tanıyır — «gəlmədi»
    ilə istifadə olunmuş sayılan cəhd YENİDƏN sayılmır (``models.retake.consumes_attempt``)."""
    if not can_decide(actor, organization):
        raise PermissionDenied
    with retake_files.discard_on_error():
        application = lock(application_id, organization)
        if application.refund_state:
            raise ValidationError(pgettext(_CTX, "Bu müraciət üzrə qaytarılma qərarı artıq verilib."))
        if not is_refundable(application):
            raise ValidationError(
                pgettext(
                    _CTX,
                    "Qaytarılma qərarı yalnız ödənişi təsdiqlənmiş və sonra rədd edilmiş, «İmtahana gəlmədi» və ya "
                    "qərarla geri götürülmüş 25% müraciətinə verilir.",
                )
            )
        text = retake_rules.clean_reason(reason)
        decision = retake_closure.clean_decision(
            order_number=order_number,
            order_date=order_date,
            document=document,
            missing_message=pgettext(
                _CTX, "Qaytarılma rəsmi qərarla olur: əmr nömrəsi və tarixi və ya qərar sənədi əlavə edin."
            ),
        )
        value = _clean_amount(amount, application.paid_amount)
        if decision["document"] is not None:
            application.refund_document.save(
                getattr(decision["document"], "name", "") or "refund", decision["document"], save=False
            )
            retake_files.track(application.refund_document)
        application.refund_state = RetakeRefundState.DECIDED
        application.refund_amount = value
        application.refund_reason = text
        application.refund_order_number = decision["number"]
        application.refund_order_date = decision["date"]
        application.refund_decided_by = actor
        application.refund_decided_at = timezone.now()
        application.refund_restores_attempt = bool(restores_attempt)
        application.save(
            update_fields=[
                "refund_restores_attempt",
                "refund_state",
                "refund_amount",
                "refund_reason",
                "refund_order_number",
                "refund_order_date",
                "refund_document",
                "refund_decided_by",
                "refund_decided_at",
                "updated_at",
            ]
        )
        metadata = {
            "refund": "decided",
            "refund_amount": _metadata_money(value),
            "paid_amount": _metadata_money(application.paid_amount),
            "partial": application.paid_amount is not None and value < application.paid_amount,
            "order_number": decision["number"],
            "order_date": decision["date"].isoformat() if decision["date"] else None,
            "document": application.refund_document.name or None,
            "restores_attempt": application.refund_restores_attempt,
            "consumed_before": application.status == RetakeStatus.NO_SHOW,
        }
        record_event(
            application,
            action=RetakeEventAction.REFUND_DECIDED,
            actor=actor,
            role=RetakeActorRole.DEANERY,
            note=text,
            metadata=metadata,
        )
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=application,
            reason="retake_refund_decided",
            request=request,
            resource_type="retake_application",
            resource_id=str(application.pk),
            old_values={"refund_state": ""},
            new_values={"refund_state": RetakeRefundState.DECIDED, **metadata},
        )
    retake_notify.notify_refund(application, stage="decided", staff_key=retake_rules.PERM_PAYMENT_VERIFY)
    return application


def _clean_refund_date(raw, application) -> datetime.date:
    if isinstance(raw, datetime.date):
        value = raw
    else:
        text = str(raw or "").strip()
        if not text:
            raise ValidationError(pgettext(_CTX, "Qaytarılma tarixini yazın."))
        try:
            value = datetime.date.fromisoformat(text)
        except ValueError:
            raise ValidationError(pgettext(_CTX, "Qaytarılma tarixi düzgün deyil.")) from None
    if value > timezone.localdate():
        raise ValidationError(pgettext(_CTX, "Qaytarılma tarixi gələcəkdə ola bilməz."))
    decided = timezone.localdate(application.refund_decided_at) if application.refund_decided_at else None
    if decided is not None and value < decided:
        raise ValidationError(pgettext(_CTX, "Qaytarılma tarixi qərar tarixindən əvvəl ola bilməz."))
    return value


@transaction.atomic
def mark_refunded(*, actor, organization, application_id, refunded_on, reference, note="", request=None):
    """Mühasibatlıq — «Qaytarıldı» (tarix + arayış №); bir dəfə, yalnız qərar verilmiş müraciətdə."""
    if not can_mark(actor, organization):
        raise PermissionDenied
    application = lock(application_id, organization)
    if application.refund_state == RetakeRefundState.REFUNDED:
        raise ValidationError(pgettext(_CTX, "Ödəniş artıq qaytarılmış kimi qeyd olunub."))
    if application.refund_state != RetakeRefundState.DECIDED:
        raise ValidationError(pgettext(_CTX, "Bu müraciət üzrə qaytarılma qərarı yoxdur."))
    day = _clean_refund_date(refunded_on, application)
    text = str(reference or "").strip()[:REFERENCE_MAX]
    if not text:
        raise ValidationError(pgettext(_CTX, "Bank arayışı və ya ödəniş tapşırığı nömrəsini yazın."))
    comment = str(note or "").strip()[:2000]
    application.refund_state = RetakeRefundState.REFUNDED
    application.refunded_on = day
    application.refund_reference = text
    application.refunded_by = actor
    application.refunded_at = timezone.now()
    application.save(
        update_fields=["refund_state", "refunded_on", "refund_reference", "refunded_by", "refunded_at", "updated_at"]
    )
    metadata = {
        "refund": "refunded",
        "refund_amount": _metadata_money(application.refund_amount),
        "refunded_on": day.isoformat(),
        "refund_reference": text,
    }
    record_event(
        application,
        action=RetakeEventAction.REFUNDED,
        actor=actor,
        role=RetakeActorRole.ACCOUNTING,
        note=comment,
        metadata=metadata,
    )
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=application,
        reason="retake_refunded",
        request=request,
        resource_type="retake_application",
        resource_id=str(application.pk),
        old_values={"refund_state": RetakeRefundState.DECIDED},
        new_values={"refund_state": RetakeRefundState.REFUNDED, **metadata},
    )
    retake_notify.notify_refund(application, stage="refunded")
    return application


__all__ = ["REFUNDABLE_STATUSES", "can_decide", "can_mark", "decide", "is_refundable", "mark_refunded"]
