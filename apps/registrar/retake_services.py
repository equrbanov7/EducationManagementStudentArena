"""25% / alt qrup müraciəti — TƏLƏBƏ əməlləri + ortaq keçid köməkçisi (sahib 2026-10-18).

Hər yazı ``transaction.atomic()`` içindədir və müraciət sətri ``SELECT … FOR UPDATE`` ilə kilidlənir;
hər status keçidi :func:`transition` ilə gedir — o, ``retake_rules.assert_transition`` qapısını yoxlayır,
sahəni yazır, append-only ``RetakeApplicationEvent`` sətri yaradır, audit jurnalına yazır və tələbəyə
bildiriş göndərir (tranzaksiya bitəndən sonra). Heyət qərarları :mod:`apps.registrar.retake_decisions`-dadır.
"""

from __future__ import annotations

import hashlib

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.upload_security import validate_uploaded_file

from . import retake_eligibility, retake_files, retake_notify, retake_rules
from .models import (
    RetakeActorRole,
    RetakeApplication,
    RetakeApplicationEvent,
    RetakeEventAction,
    RetakeKind,
    RetakeReceipt,
    RetakeStatus,
    StudentAcademicRecord,
)
from .models.retake import RETAKE_FILE_EXTENSIONS, RETAKE_FILE_MAX_MB

_CTX = "registrar.retake"


def actor_label(user) -> str:
    if user is None:
        return ""
    return ((user.get_full_name() or "").strip() or getattr(user, "username", ""))[:200]


def lock(application_id, organization) -> RetakeApplication:
    application = (
        RetakeApplication.objects.select_for_update(of=("self",))
        .select_related("subject", "student", "organization", "enrollment", "enrollment__offering")
        .filter(pk=application_id, organization=organization)
        .first()
    )
    if application is None:
        raise RetakeApplication.DoesNotExist
    return application


def record_event(application, *, action, actor, role, from_status="", to_status="", note="", metadata=None):
    return RetakeApplicationEvent.objects.create(
        organization_id=application.organization_id,
        application=application,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        actor_name=actor_label(actor),
        actor_role=role,
        note=(note or "")[:4000],
        metadata=metadata or {},
    )


def transition(application, target, *, action, actor, role, note="", metadata=None, fields=(), request=None):
    """Status keçidi + hadisə + audit + tələbə bildirişi (çağıran tranzaksiyanın içində)."""
    current = application.status
    retake_rules.assert_transition(current, target)
    application.status = target
    if target not in retake_rules.TRANSITIONS or not retake_rules.TRANSITIONS[target]:
        application.closed_at = timezone.now()
        fields = (*fields, "closed_at")
    application.save(update_fields=["status", "updated_at", *fields])
    event = record_event(
        application,
        action=action,
        actor=actor,
        role=role,
        from_status=current,
        to_status=target,
        note=note,
        metadata=metadata,
    )
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=application.organization,
        obj=application,
        reason=f"retake_{action}",
        request=request,
        resource_type="retake_application",
        resource_id=str(application.pk),
        old_values={"status": current},
        new_values={"status": target, **(metadata or {})},
    )
    retake_notify.notify_student(application, note=note if target == RetakeStatus.PAYMENT_REJECTED else "")
    return event


# ── Qəbz faylı ───────────────────────────────────────────────────────────────


def _file_digest(uploaded) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in uploaded.chunks():
        digest.update(chunk)
        size += len(chunk)
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    return digest.hexdigest(), size


def clean_upload(uploaded):
    """Uzantı (pdf/jpg/png), ölçü (10 MB), imza/MIME — ``core.upload_security`` ilə."""
    if uploaded is None:
        raise ValidationError(pgettext(_CTX, "Fayl seçilməyib."))
    validate_uploaded_file(uploaded, allowed_extensions=RETAKE_FILE_EXTENSIONS, max_size_mb=RETAKE_FILE_MAX_MB)
    return uploaded


def _store_receipt(application, uploaded, *, by_user) -> RetakeReceipt:
    clean_upload(uploaded)
    sha256, size = _file_digest(uploaded)
    original = str(getattr(uploaded, "name", "") or "")[:255]
    receipt = RetakeReceipt(
        organization_id=application.organization_id,
        application=application,
        sha256=sha256,
        size=size,
        original_name=original,
        uploaded_by=by_user,
    )
    receipt.file.save(original or "receipt", uploaded, save=False)
    retake_files.track(receipt.file)
    receipt.save()
    return receipt


def duplicate_receipt_map(receipts) -> dict:
    """``receipt_id`` → eyni SHA-256 ilə BAŞQA müraciətdə yüklənmiş qəbzlər (tək sorğu)."""
    receipts = [r for r in receipts if r is not None and r.sha256]
    if not receipts:
        return {}
    by_hash: dict = {}
    for receipt in receipts:
        by_hash.setdefault((receipt.organization_id, receipt.sha256), []).append(receipt)
    hashes = {key[1] for key in by_hash}
    org_ids = {key[0] for key in by_hash}
    others = list(
        RetakeReceipt.objects.filter(organization_id__in=org_ids, sha256__in=hashes)
        .select_related("application", "application__student", "application__subject")
        .order_by("created_at")
    )
    result: dict = {}
    for receipt in receipts:
        matches = [
            other
            for other in others
            if other.sha256 == receipt.sha256
            and other.organization_id == receipt.organization_id
            and other.application_id != receipt.application_id
        ]
        if matches:
            result[receipt.id] = matches
    return result


# ── Tələbə əməlləri ──────────────────────────────────────────────────────────


def _student_group_id(student, organization):
    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=student, is_active=True)
        .order_by("-created_at")
        .values_list("group_id", flat=True)
        .first()
    )


def apply(*, student, organization, enrollment_id, kind, note="", receipt=None, request=None) -> RetakeApplication:
    """Kəsr fənn üzrə müraciət (25% — qəbz indi və ya sonra; alt qrup — ödənişsiz)."""
    if kind not in RetakeKind.values:
        raise ValidationError(pgettext(_CTX, "Müraciət növü seçilməyib."))
    if not retake_rules.applications_open(organization):
        raise ValidationError(pgettext(_CTX, "Müraciət pəncərəsi hazırda bağlıdır."))
    row = retake_eligibility.row_for_enrollment(student=student, organization=organization, enrollment_id=enrollment_id)
    if row is None:
        raise ValidationError(
            pgettext(_CTX, "Bu fənn üzrə müraciət etmək mümkün deyil — fənn kəsr siyahısında yoxdur.")
        )
    option = row["options"][kind]
    if not option["allowed"]:
        raise ValidationError(option["why"])
    if receipt is not None and kind != RetakeKind.RETAKE_25:
        raise ValidationError(pgettext(_CTX, "Alt qrup müraciətinə ödəniş qəbzi tələb olunmur."))
    if receipt is not None:
        clean_upload(receipt)
    result = row["result"]
    fee = {"amount": None, "inputs": {}}
    if kind == RetakeKind.RETAKE_25:
        from . import retake_fees

        fee = retake_fees.estimate(
            context=retake_fees.student_context(student, organization), period=row["period"], subject=row["subject"]
        )
    try:
        with retake_files.discard_on_error(), transaction.atomic():
            application = RetakeApplication.objects.create(
                organization=organization,
                student=student,
                enrollment=row["enrollment"],
                subject=row["subject"],
                period=row["period"],
                student_group_id=_student_group_id(student, organization),
                kind=kind,
                status=RetakeStatus.SUBMITTED,
                attempt_number=row["attempts_used"] + 1 if kind == RetakeKind.RETAKE_25 else 0,
                student_note=(note or "").strip()[:2000],
                eligibility=retake_eligibility.snapshot(row),
                base_exam_score=result.get("effective_exam"),
                base_total=result.get("total"),
                expected_fee=fee["amount"],
                fee_inputs=fee["inputs"],
            )
            record_event(
                application,
                action=RetakeEventAction.SUBMITTED,
                actor=student,
                role=RetakeActorRole.STUDENT,
                to_status=RetakeStatus.SUBMITTED,
                note=application.student_note,
                # Tələbəyə göstərilən təxmini məbləğ append-only hadisədə də qalır (review 2026-10-19, M-3).
                metadata={
                    "kind": kind,
                    "eligibility": application.eligibility,
                    "expected_fee": str(fee["amount"]) if fee["amount"] is not None else None,
                    "fee_inputs": fee["inputs"],
                },
            )
            log_action(
                AuditAction.CREATE,
                user=student,
                organization=organization,
                obj=application,
                reason="retake_submitted",
                request=request,
                resource_type="retake_application",
                resource_id=str(application.pk),
                new_values={"kind": kind, "subject_id": str(application.subject_id)},
            )
            if receipt is not None:
                _attach_receipt(application, receipt, student=student, request=request)
            else:
                retake_notify.notify_student(application)
                if kind == RetakeKind.SUBGROUP:
                    retake_notify.notify_staff_queue(application, retake_rules.PERM_MANAGE)
    except IntegrityError as exc:
        raise ValidationError(pgettext(_CTX, "Bu fənn üzrə aktiv müraciətiniz artıq var.")) from exc
    return application


def _attach_receipt(application, uploaded, *, student, request=None):
    receipt = _store_receipt(application, uploaded, by_user=student)
    application.current_receipt = receipt
    transition(
        application,
        RetakeStatus.PAYMENT_PENDING_REVIEW,
        action=RetakeEventAction.RECEIPT_UPLOADED,
        actor=student,
        role=RetakeActorRole.STUDENT,
        metadata={"receipt_id": str(receipt.pk), "sha256": receipt.sha256, "size": receipt.size},
        fields=("current_receipt",),
        request=request,
    )
    retake_notify.notify_staff_queue(application, retake_rules.PERM_PAYMENT_VERIFY)
    return receipt


def _own(application, student):
    if application.student_id != getattr(student, "pk", None):
        raise PermissionDenied


@transaction.atomic
def upload_receipt(*, student, organization, application_id, receipt, request=None) -> RetakeApplication:
    application = lock(application_id, organization)
    _own(application, student)
    if application.kind != RetakeKind.RETAKE_25:
        raise ValidationError(pgettext(_CTX, "Alt qrup müraciətinə ödəniş qəbzi tələb olunmur."))
    if application.status not in retake_rules.RECEIPT_UPLOADABLE:
        raise ValidationError(pgettext(_CTX, "Qəbz yalnız ödəniş yoxlanmazdan əvvəl və ya rəddən sonra yüklənir."))
    with retake_files.discard_on_error():
        _attach_receipt(application, receipt, student=student, request=request)
    return application


@transaction.atomic
def withdraw(*, student, organization, application_id, note="", request=None) -> RetakeApplication:
    application = lock(application_id, organization)
    _own(application, student)
    if application.status not in retake_rules.WITHDRAWABLE:
        raise ValidationError(pgettext(_CTX, "Qərar verilmiş müraciəti geri götürmək olmaz."))
    transition(
        application,
        RetakeStatus.WITHDRAWN,
        action=RetakeEventAction.WITHDRAWN,
        actor=student,
        role=RetakeActorRole.STUDENT,
        note=(note or "").strip()[:2000],
        request=request,
    )
    return application


__all__ = [
    "actor_label",
    "apply",
    "clean_upload",
    "duplicate_receipt_map",
    "lock",
    "record_event",
    "transition",
    "upload_receipt",
    "withdraw",
]
