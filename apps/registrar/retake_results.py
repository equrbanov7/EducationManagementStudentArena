"""25% təkrar imtahanın NƏTİCƏSİ — ``ResitRecord`` + müraciətin ``result_*`` sahələri (sahib 2026-10-18).

İki yazı yolu var, başqası YOXDUR (rəy 2026-10-18, HIGH-1):

* **Dekanlıq / İmtahan mərkəzi «Nəticə»** (:func:`record_result`) — kağız / yazılı / praktiki 25% imtahanı;
  ``admitted`` və ya ``exam_granted`` müraciətinə, ``retake.manage`` və ya ``final_score.entry`` ilə;
* **İmtahan körpüsü** (:func:`record_attempt_result`) — «İmtahan şansı ver» (səbəb «25% müraciəti») qeydindən
  SONRA başlanmış onlayn cəhdin balı (``exam_bridge.record_exam_result(attempt=…)``). Yalnız ``exam_granted``
  müraciəti tamamlanır; tamamlanmış müraciətdə həmin cəhdin YENİDƏN yoxlanması / apellyasiyası nəticəni
  yeniləyir (``RESULT_RECORDED`` hadisəsi əlavə olunur — HIGH-2). Bal köhnə ilə EYNİ olsa da yazılır (MEDIUM-3).

Əsas imtahanın düzəlişi (jurnal, toplu bal daxiletməsi, əsas cəhdin apellyasiyası) müraciətə və
``ResitRecord``-a HEÇ VAXT toxunmur. 25% balı ``FinalGrade.exam_score``-a YAZILMIR — orada əsas imtahanın
balı qalır («əvvəlki nəticə»), qüvvədə olan nəticə ``compute_final_result``-un mövcud qaydası ilə
``ResitRecord.resit_score``-dan gəlir.

Bal sxemin tavanından (``exam_score_max``, adətən 50) böyükdürsə RƏDD edilir (səssiz kəsmə yoxdur — LOW-7).

Audit fail-closed (rəy 2026-10-21, R08): ``ResitRecord`` balının audit sətri yazılmasa
``audit_write.AuditWriteFailed`` atılır və hər iki yolun tranzaksiyası geri qayıdır (müraciət də dəyişmir).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from . import finals, grade_audit, gradebook, retake_rules
from .models import (
    Enrollment,
    ExamChanceGrant,
    ExamChanceReason,
    ResitReason,
    ResitRecord,
    ResitStatus,
    RetakeActorRole,
    RetakeEventAction,
    RetakeKind,
    RetakeResultSource,
    RetakeStatus,
)
from .retake_services import lock, record_event, transition

_CTX = "registrar.retake"

_RESULT_FIELDS = (
    "resit_record",
    "result_score",
    "result_total",
    "result_letter",
    "result_passed",
    "result_source",
    "result_recorded_at",
    "result_recorded_by",
)


def score_cap(application) -> int:
    scheme = gradebook.ensure_assessment_scheme(offering=application.enrollment.offering)
    return finals.exam_score_max(scheme)


def clean_score(raw, *, cap) -> Decimal:
    try:
        value = Decimal(str(raw).strip().replace(",", "."))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError(pgettext(_CTX, "Bal rəqəm olmalıdır.")) from None
    if not value.is_finite() or value < 0:
        raise ValidationError(pgettext(_CTX, "Bal mənfi ola bilməz."))
    if value > Decimal(cap):
        raise ValidationError(
            pgettext(_CTX, "Bal bu fənnin imtahan tavanından ({cap}) çox ola bilməz.").format(cap=cap)
        )
    return value


def _write_resit(application, score, *, by_user, request=None):
    enrollment = application.enrollment
    Enrollment.objects.select_for_update().filter(pk=enrollment.pk).exists()
    resit = ResitRecord.objects.filter(enrollment=enrollment).first()
    old = resit.resit_score if resit else None
    if resit is None:
        reason = {"qb": ResitReason.ABSENCE, "exam25": ResitReason.EXAM}.get(
            (application.eligibility or {}).get("fail_reason"), ResitReason.TOTAL
        )
        resit = ResitRecord.objects.create(
            organization_id=enrollment.organization_id, enrollment=enrollment, reason=reason, decided_by=by_user
        )
    resit.resit_score = score
    resit.status = ResitStatus.COMPLETED
    resit.decided_by = by_user
    resit.save(update_fields=["resit_score", "status", "decided_by", "updated_at"])
    if old != score:
        grade_audit.log_grade_changes(
            offering=enrollment.offering,
            by_user=by_user,
            kind="resit",
            changes=[
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": f"25% təkrar imtahan ({application.attempt_number}-ci cəhd)",
                    "old": grade_audit.score_repr(old),
                    "new": grade_audit.score_repr(score),
                }
            ],
            request=request,
            fail_closed=True,  # R08 (2026-10-21): 25% balı audit sətri olmadan commit olunmur
        )
    return resit


def _apply(application, score, *, actor, role, source, note="", metadata=None, request=None):
    """Nəticəni yaz: ``exam_granted`` / ``admitted`` → ``completed``; ``completed`` → yalnız yenilə + hadisə."""
    resit = _write_resit(application, score, by_user=actor, request=request)
    result = finals.compute_final_result(enrollment=application.enrollment)
    previous = application.result_score
    application.resit_record = resit
    application.result_score = score
    application.result_total = result["total"]
    application.result_letter = result["letter"] or ""
    application.result_passed = bool(result["passed"])
    application.result_source = source
    application.result_recorded_at = timezone.now()
    application.result_recorded_by = actor
    payload = {
        "score": str(score),
        "previous_score": str(previous) if previous is not None else None,
        "total": str(result["total"]),
        "passed": bool(result["passed"]),
        "base_exam_score": str(application.base_exam_score) if application.base_exam_score is not None else None,
        "source": source,
        **(metadata or {}),
    }
    if application.status == RetakeStatus.COMPLETED:
        application.save(update_fields=["updated_at", *_RESULT_FIELDS])
        record_event(
            application,
            action=RetakeEventAction.RESULT_RECORDED,
            actor=actor,
            role=role,
            from_status=application.status,
            to_status=application.status,
            note=(note or "").strip()[:2000],
            metadata=payload,
        )
        return application
    transition(
        application,
        RetakeStatus.COMPLETED,
        action=RetakeEventAction.RESULT_RECORDED,
        actor=actor,
        role=role,
        note=(note or "").strip()[:2000],
        metadata=payload,
        fields=_RESULT_FIELDS,
        request=request,
    )
    return application


@transaction.atomic
def record_result(*, actor, organization, application_id, score, note="", request=None):
    """Desk «Nəticə» — kağız / yazılı / praktiki 25% imtahanı (``admitted`` / ``exam_granted``)."""
    application = lock(application_id, organization)
    if application.kind != RetakeKind.RETAKE_25 or application.status not in retake_rules.RESULT_RECORDABLE:
        raise ValidationError(pgettext(_CTX, "Nəticə yalnız imtahana buraxılmış 25% müraciətinə yazılır."))
    value = clean_score(score, cap=score_cap(application))
    return _apply(
        application,
        value,
        actor=actor,
        role=RetakeActorRole.DEANERY,
        source=RetakeResultSource.MANUAL,
        note=note,
        request=request,
    )


def application_for_attempt(*, student, subject_id, organization, attempt):
    """Bu onlayn cəhd 25% cəhdidirmi? — «25% müraciəti» şans qeydindən SONRA başlanmış həmin imtahanın cəhdi.

    Uyğun müraciət (STATUSUNDAN ASILI OLMAYARAQ — review 2026-10-19, HIGH-1: bağlanmış müraciətin cəhdi də 25%
    cəhdidir və əsas imtahan balına düşməməlidir) və ya ``None``. Status qərarını çağıran verir
    (``exam_bridge``: ``exam_granted`` / ``completed`` → nəticə yazılır, bağlanmış → heç nə yazılmır).
    ``exam_attempt_history.retake_attempt_ids`` ilə EYNİ qayda (şans qeydi ≤ cəhdin başlanğıcı)."""
    if attempt is None or student is None or organization is None or not subject_id:
        return None
    started = getattr(attempt, "started_at", None) or getattr(attempt, "finished_at", None)
    if started is None:
        return None
    grant = (
        ExamChanceGrant.objects.filter(
            organization=organization,
            student=student,
            exam_id=attempt.exam_id,
            reason=ExamChanceReason.RETAKE_25,
            application__isnull=False,
            application__subject_id=subject_id,
            application__kind=RetakeKind.RETAKE_25,
            created_at__lte=started,
        )
        .select_related("application")
        .order_by("-created_at")
        .first()
    )
    return grant.application if grant is not None else None


#: Bu statuslarda 25% cəhdinin balı müraciətə yazılır; qalanlarda (bağlanmış) heç nə yazılmır.
RESULT_ACCEPTING = frozenset({RetakeStatus.EXAM_GRANTED, RetakeStatus.COMPLETED})


@transaction.atomic
def record_attempt_result(*, application, score, attempt, by_user=None, appeal_id=None):
    """İmtahan körpüsü: 25% cəhdinin balı (ilk yazı və ya sonrakı yoxlama / apellyasiya)."""
    application = lock(application.pk, application.organization)
    if application.status not in RESULT_ACCEPTING:
        return application
    value = clean_score(score, cap=score_cap(application))
    metadata = {"attempt_id": getattr(attempt, "pk", None), "exam_id": getattr(attempt, "exam_id", None)}
    if appeal_id:
        metadata["appeal_id"] = appeal_id
    _apply(
        application,
        value,
        actor=by_user,
        role=RetakeActorRole.EXAM_CENTER,
        source=RetakeResultSource.EXAM_ENTRY,
        metadata=metadata,
    )
    return application


__all__ = [
    "RESULT_ACCEPTING",
    "application_for_attempt",
    "clean_score",
    "record_attempt_result",
    "record_result",
    "score_cap",
]
