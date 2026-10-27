"""25% / alt qrup müraciəti — HEYƏT qərarları, nəticə və imtahan şansı ilə əlaqə (sahib 2026-10-18).

* **Mühasibatlıq** (``retake.payment_verify``): ödənişi təsdiqləyir (bank arayışı / ödəniş № ilə) və ya
  səbəblə rədd edir. Eyni qəbz başqa müraciətdə də yüklənibsə bu BLOK deyil — xəbərdarlıq hadisənin
  metadata-sına yazılır, qərar mühasibindir.
* **Dekanlıq / tədris şöbəsi** (``retake.manage``): 25%-ə buraxır / rədd edir; alt qrup müraciətini
  SƏNƏDLƏ təsdiqləyir və tələbəni rəsmi servislə yerləşdirir (``registrar.public.place_in_subgroup`` —
  paralel agentin modulu; hələ yoxdursa qərar yazılır, yerləşdirmə «gözləyir» qalır).
* **Nəticə** (:mod:`apps.registrar.retake_results`): ``ResitRecord.resit_score``-a yazılır (``compute_final_result``-un MÖVCUD qaydası: tamamlanmış
  təkrar imtahan əsas imtahan balını əvəz edir → transkript «son qüvvədə olan» nəticəni göstərir). Jurnal
  kilidi bu yolu BLOKLAMIR — ``finals.set_exam_score`` ilə eyni əsas: jurnal semestr sonunda bağlanır,
  25% imtahanı ondan SONRA keçir. Hər cəhdin balı müraciətin öz ``result_*`` sahələrində qalır.
* **İmtahan şansı** («İmtahan şansı ver», səbəb «25% müraciəti»): ``admitted`` → ``exam_granted``;
  həmin şansdan SONRA başlanmış onlayn cəhdin balını imtahan körpüsü ``retake_results``-a ötürür.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core import superadmin_waiver

from . import retake_fees, retake_files, retake_notify, retake_rules
from .models import (
    Enrollment,
    RetakeActorRole,
    RetakeApplication,
    RetakeEventAction,
    RetakeKind,
    RetakeStatus,
)
from .models.retake import consumed_attempt_q
from .retake_results import record_result  # noqa: F401 — nəticə yazısı ``retake_results``-dadır (geriyə uyğun ad)
from .retake_services import clean_upload, duplicate_receipt_map, lock, transition

logger = logging.getLogger(__name__)

_CTX = "registrar.retake"


class SubgroupPlacementUnavailable(Exception):
    """Yerləşdirmə servisi (``registrar.public.place_in_subgroup``) hələ quraşdırılmayıb."""


# ── Mühasibatlıq ─────────────────────────────────────────────────────────────


@transaction.atomic
def verify_payment(
    *, actor, organization, application_id, paid_amount=None, payment_reference="", note="", request=None
):
    """Ödənişi təsdiqlə. 2026-10-19 (sahib): mühasib ÖDƏNİLƏN məbləği yazır; gözlənilən məbləğ (təhsil haqqı
    cədvəli + düstur) bu anda yenidən hesablanır, ikisi və düsturun girişləri hadisəyə (append-only) yazılır.
    Fərq XƏBƏRDARLIQDIR — təsdiqi bloklamır."""
    application = lock(application_id, organization)
    if application.status != RetakeStatus.PAYMENT_PENDING_REVIEW:
        raise ValidationError(pgettext(_CTX, "Bu müraciətdə yoxlanacaq qəbz yoxdur."))
    paid = retake_fees.clean_amount(paid_amount, positive=True)
    # Müraciət anında tələbəyə göstərilən məbləğ (snapshot) və təsdiq anındakı yenidən hesab AYRI saxlanılır.
    # Yenidən hesab ``None`` olarsa köhnə məbləğ və ONUN girişləri qalır (cüt bir-birinə uyğun qalsın).
    expected_at_submit = application.expected_fee
    inputs_at_submit = application.fee_inputs or {}
    fee = retake_fees.for_application(application)
    expected = fee["amount"] if fee["amount"] is not None else expected_at_submit
    receipt = application.current_receipt
    duplicates = duplicate_receipt_map([receipt]).get(getattr(receipt, "id", None), [])
    application.payment_reference = (payment_reference or "").strip()[:120]
    application.payment_verified_by = actor
    application.payment_verified_at = timezone.now()
    application.paid_amount = paid
    application.expected_fee = expected
    if fee["amount"] is not None:
        application.fee_inputs = fee["inputs"]
    transition(
        application,
        RetakeStatus.PAYMENT_VERIFIED,
        action=RetakeEventAction.PAYMENT_VERIFIED,
        actor=actor,
        role=RetakeActorRole.ACCOUNTING,
        note=(note or "").strip()[:2000],
        metadata={
            "payment_reference": application.payment_reference,
            "receipt_id": str(getattr(receipt, "pk", "") or ""),
            "duplicate_receipt_applications": sorted({str(d.application_id) for d in duplicates}),
            "paid_amount": str(paid),
            "expected_fee": str(expected) if expected is not None else None,
            "expected_at_submit": str(expected_at_submit) if expected_at_submit is not None else None,
            "expected_at_verify": str(fee["amount"]) if fee["amount"] is not None else None,
            "amount_mismatch": expected is not None and paid != expected,
            "fee_inputs": application.fee_inputs,
            "fee_inputs_at_submit": inputs_at_submit,
            "fee_inputs_at_verify": fee["inputs"],
        },
        fields=(
            "payment_reference",
            "payment_verified_by",
            "payment_verified_at",
            "paid_amount",
            "expected_fee",
            "fee_inputs",
        ),
        request=request,
    )
    retake_notify.notify_staff_queue(application, retake_rules.PERM_MANAGE)
    return application


@transaction.atomic
def reject_payment(*, actor, organization, application_id, reason, request=None):
    application = lock(application_id, organization)
    if application.status != RetakeStatus.PAYMENT_PENDING_REVIEW:
        raise ValidationError(pgettext(_CTX, "Bu müraciətdə yoxlanacaq qəbz yoxdur."))
    text = retake_rules.clean_reason(reason)
    receipt = application.current_receipt
    duplicates = duplicate_receipt_map([receipt]).get(getattr(receipt, "id", None), [])
    transition(
        application,
        RetakeStatus.PAYMENT_REJECTED,
        action=RetakeEventAction.PAYMENT_REJECTED,
        actor=actor,
        role=RetakeActorRole.ACCOUNTING,
        note=text,
        metadata={
            "receipt_id": str(getattr(receipt, "pk", "") or ""),
            "duplicate_receipt_applications": sorted({str(d.application_id) for d in duplicates}),
        },
        request=request,
    )
    return application


# ── Dekanlıq / tədris şöbəsi ─────────────────────────────────────────────────


def _consumed_attempts(application) -> int:
    return (
        RetakeApplication.objects.filter(
            organization_id=application.organization_id,
            student_id=application.student_id,
            subject_id=application.subject_id,
            kind=RetakeKind.RETAKE_25,
        )
        .filter(consumed_attempt_q())  # qaytarılma qərarı cəhdi bərpa edibsə sayılmır (2026-10-19)
        .exclude(pk=application.pk)
        .count()
    )


@transaction.atomic
def admit(*, actor, organization, application_id, note="", request=None):
    """25% müraciəti: ödəniş təsdiqləndikdən sonra imtahana buraxılış (cəhd limiti YENİDƏN yoxlanır)."""
    application = lock(application_id, organization)
    if application.kind != RetakeKind.RETAKE_25:
        raise ValidationError(pgettext(_CTX, "Alt qrup müraciəti sənədlə təsdiqlənir."))
    if application.status != RetakeStatus.PAYMENT_VERIFIED:
        raise ValidationError(pgettext(_CTX, "Buraxılış yalnız ödəniş təsdiqləndikdən sonra mümkündür."))
    used = _consumed_attempts(application)
    limit = retake_rules.max_attempts()
    if used >= limit:
        raise ValidationError(
            pgettext(_CTX, "Bu fənn üzrə 25% cəhd limiti dolub ({used}/{limit}).").format(used=used, limit=limit)
        )
    application.attempt_number = used + 1
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.decision_note = (note or "").strip()[:2000]
    transition(
        application,
        RetakeStatus.ADMITTED,
        action=RetakeEventAction.ADMITTED,
        actor=actor,
        role=RetakeActorRole.DEANERY,
        note=application.decision_note,
        metadata={"attempt_number": application.attempt_number, "attempts_limit": limit},
        fields=("attempt_number", "decided_by", "decided_at", "decision_note"),
        request=request,
    )
    return application


@transaction.atomic
def reject(
    *, actor, organization, application_id, reason, order_number="", order_date=None, document=None, request=None
):
    """Rədd. Alt qrup (ödənişsiz) — səbəblə; 25% (ödənişdən sonra) — ``retake_closure`` ilə RƏSMİ QƏRARLA."""
    application = lock(application_id, organization)
    if application.kind == RetakeKind.RETAKE_25:
        from . import retake_closure

        return retake_closure.close(
            actor=actor,
            organization=organization,
            application_id=application.pk,
            action="reject",
            reason=reason,
            order_number=order_number,
            order_date=order_date,
            document=document,
            request=request,
        )
    allowed = {RetakeStatus.SUBMITTED}
    if application.status not in allowed:
        raise ValidationError(pgettext(_CTX, "Bu mərhələdə dekanlıq qərarı verilmir."))
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.decision_note = retake_rules.clean_reason(reason)
    transition(
        application,
        RetakeStatus.REJECTED,
        action=RetakeEventAction.REJECTED,
        actor=actor,
        role=RetakeActorRole.DEANERY,
        note=application.decision_note,
        fields=("decided_by", "decided_at", "decision_note"),
        request=request,
    )
    return application


def _placement_service():
    from apps.registrar import public

    service = getattr(public, "place_in_subgroup", None)
    if not callable(service):
        raise SubgroupPlacementUnavailable
    return service


def _placement_error_class():
    from apps.registrar import public

    return getattr(public, "SubgroupPlacementError", None)


def _place(application, *, actor, offering, document, reason, request):
    """Rəsmi yerləşdirmə servisi — xəta ``ValidationError``-a çevrilir (kodu ilə), tranzaksiya geri qaytarılır."""
    service = _placement_service()
    error_class = _placement_error_class()
    try:
        placed = service(
            student=application.student,
            offering=offering,
            document=document,
            actor=actor,
            reason=reason,
            request=request,
        )
    except Exception as exc:  # noqa: BLE001 — yalnız servisin öz xətası tutulur
        if error_class is not None and isinstance(exc, error_class):
            code = getattr(exc, "code", "") or ""
            raise ValidationError(f"{exc}" + (f" [{code}]" if code else ""), code=code or None) from exc
        raise
    application.target_offering = offering
    # Servis müqaviləsi: ``{"event", "enrollment", "credit", "warnings", "retake", "released"}`` (köhnə/mok: Enrollment).
    enrollment = placed.get("enrollment") if isinstance(placed, dict) else placed
    if isinstance(enrollment, Enrollment):
        application.placement_enrollment = enrollment
    transition(
        application,
        RetakeStatus.COMPLETED,
        action=RetakeEventAction.PLACED,
        actor=actor,
        role=RetakeActorRole.DEANERY,
        note=reason,
        metadata={"offering_id": str(offering.pk), "enrollment_id": str(getattr(enrollment, "pk", "") or "")},
        fields=("target_offering", "placement_enrollment"),
        request=request,
    )


def _offering_for(application, offering_id):
    from .models import CourseOffering

    if not offering_id:
        return None
    offering = (
        CourseOffering.objects.select_related("subject", "period", "group")
        .filter(pk=offering_id, organization_id=application.organization_id, subject_id=application.subject_id)
        .first()
    )
    if offering is None:
        raise ValidationError(pgettext(_CTX, "Seçilmiş jurnal bu fənnə aid deyil."))
    return offering


def _waiver_reason(reason, actor, document):
    """Superadmin sənədsiz qərar verirsə səbəbə avtomatik «Superadmin düzəlişi — sənədsiz» qeydi düşür."""
    if document is not None:
        return reason
    return superadmin_waiver.stamp(reason, actor)


@transaction.atomic
def approve_subgroup(*, actor, organization, application_id, document, reason, offering_id=None, request=None):
    """Alt qrup: SƏNƏD məcburi (sahibin 2026-09-07 qaydası); hədəf jurnal verilibsə dərhal yerləşdirmə."""
    with retake_files.discard_on_error():
        application = lock(application_id, organization)
        if application.kind != RetakeKind.SUBGROUP or application.status != RetakeStatus.SUBMITTED:
            raise ValidationError(pgettext(_CTX, "Bu müraciət alt qrup qərarı gözləmir."))
        text = retake_rules.clean_reason(_waiver_reason(reason, actor, document))
        offering = _offering_for(application, offering_id)
        if document is not None or not superadmin_waiver.waives(actor):  # superadmin: sənədsiz (2026-10-27)
            clean_upload(document)
            application.decision_document.save(getattr(document, "name", "") or "document", document, save=False)
            retake_files.track(application.decision_document)
        application.decided_by = actor
        application.decided_at = timezone.now()
        application.decision_note = text
        transition(
            application,
            RetakeStatus.ADMITTED,
            action=RetakeEventAction.SUBGROUP_APPROVED,
            actor=actor,
            role=RetakeActorRole.DEANERY,
            note=text,
            metadata={"document": application.decision_document.name or None},
            fields=("decision_document", "decided_by", "decided_at", "decision_note"),
            request=request,
        )
        if offering is not None:
            try:
                _placement_service()
            except SubgroupPlacementUnavailable:
                # Paralel agentin servisi hələ yoxdur — qərar və sənəd qalır, yerləşdirmə «gözləyir».
                logger.info("retake: subgroup placement service unavailable; %s stays admitted", application.pk)
                return application
            if document is not None:
                document.seek(0)
            _place(application, actor=actor, offering=offering, document=document, reason=text, request=request)
        return application


@transaction.atomic
def place_subgroup(*, actor, organization, application_id, offering_id, document, reason, request=None):
    """Təsdiqlənmiş alt qrup müraciətinin sonradan yerləşdirilməsi (sənəd yenə məcburidir)."""
    application = lock(application_id, organization)
    if application.kind != RetakeKind.SUBGROUP or application.status != RetakeStatus.ADMITTED:
        raise ValidationError(pgettext(_CTX, "Bu müraciət yerləşdirmə gözləmir."))
    text = retake_rules.clean_reason(_waiver_reason(reason, actor, document))
    if document is not None or not superadmin_waiver.waives(actor):
        clean_upload(document)
    offering = _offering_for(application, offering_id)
    if offering is None:
        raise ValidationError(pgettext(_CTX, "Hədəf jurnal seçilməlidir."))
    try:
        _placement_service()
    except SubgroupPlacementUnavailable:
        raise ValidationError(
            pgettext(_CTX, "Alt qrupa yerləşdirmə servisi hələ aktiv deyil — sonra yenidən cəhd edin.")
        ) from None
    _place(application, actor=actor, offering=offering, document=document, reason=text, request=request)
    return application


# ── İmtahan şansı ilə əlaqə ──────────────────────────────────────────────────


def grantable_applications(*, organization, student_ids) -> dict:
    """``student_id`` → imtahan cəhdi verilə bilən 25% müraciətləri (ödəniş təsdiqlənib + buraxılıb)."""
    ids = [sid for sid in student_ids if sid]
    if not ids or organization is None:
        return {}
    rows = (
        RetakeApplication.objects.filter(
            organization=organization,
            student_id__in=ids,
            kind=RetakeKind.RETAKE_25,
            status__in=(RetakeStatus.ADMITTED, RetakeStatus.EXAM_GRANTED),
            payment_verified_at__isnull=False,
        )
        .select_related("subject", "period")
        .order_by("created_at")
    )
    grouped: dict = {}
    for application in rows:
        grouped.setdefault(application.student_id, []).append(application)
    return grouped


def mark_exam_granted(*, application, actor, grant, request=None):
    """Çağıran (``record_exam_chance``) tranzaksiyanın içindədir; ``admitted`` → ``exam_granted``."""
    application = lock(application.pk, application.organization)
    if application.status == RetakeStatus.EXAM_GRANTED:
        from .retake_services import record_event

        record_event(
            application,
            action=RetakeEventAction.EXAM_GRANTED,
            actor=actor,
            role=RetakeActorRole.EXAM_CENTER,
            from_status=application.status,
            to_status=application.status,
            metadata={"exam_id": grant.exam_id, "grant_id": str(grant.pk)},
        )
        return application
    application.exam_granted_at = timezone.now()
    transition(
        application,
        RetakeStatus.EXAM_GRANTED,
        action=RetakeEventAction.EXAM_GRANTED,
        actor=actor,
        role=RetakeActorRole.EXAM_CENTER,
        metadata={"exam_id": grant.exam_id, "exam_title": grant.exam_title, "grant_id": str(grant.pk)},
        fields=("exam_granted_at",),
        request=request,
    )
    return application


__all__ = [
    "SubgroupPlacementUnavailable",
    "admit",
    "approve_subgroup",
    "grantable_applications",
    "mark_exam_granted",
    "place_subgroup",
    "record_result",
    "reject",
    "reject_payment",
    "verify_payment",
]
