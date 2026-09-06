"""Sual göndərişinin KAFEDRA MƏRHƏLƏSİ — marşrut, qərarlar, iz və bildirişlər.

Sahibin qərarı (2026-09): müəllimin imtahan sualları (final və ya aralıq)
İmtahan Mərkəzinə BİRBAŞA getmir.  Zəncir:

    müəllim → KAFEDRA MÜDİRİ → İmtahan Mərkəzi

Bu modul zəncirin kafedra hissəsini daşıyır:

* ``route_submission_to_chair`` — göndərişi kafedraya yönləndirir (kafedra
  müdiri yoxdursa DEKANLIĞA, açıq qeyd ilə — heç vaxt səssizcə mərkəzə).
* ``chair_approve`` / ``chair_request_revision`` / ``chair_reject`` — kafedra
  qərarları.  Düzəliş və rədd üçün SƏBƏB MƏCBURİDİR (≥20 simvol).
* ``record_event`` — hər keçid ``QuestionSubmissionEvent`` sətri kimi qeyd
  olunur (əlavə-only); UI zaman xəttini məhz oradan qurur.

Bütün qərarlar ``core.audit.log_action`` ilə audit olunur və hər keçiddə
iştirakçılara (müəllim, kafedra müdir(lər)i, imtahan mərkəzi) bildiriş gedir.
Bildiriş/audit xətası əsas axını POZMUR (fail-soft, log-a düşür).
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import QuestionSubmission, QuestionSubmissionEvent
from apps.exams.services.question_chair_units import (
    can_review_submission_as_chair,
    chair_queue_filter,
    chair_route_targets,
    resolve_submission_chair_unit,
)
from core.audit import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)

#: Düzəliş/rədd səbəbinin minimal uzunluğu — «ok», «yox» kimi izsiz qərarların
#: qarşısını alır (müəllim nəyi düzəltməli olduğunu BİLMƏLİDİR).
MIN_REASON_LENGTH = 20

_EVENT_CTX = "exams.service.question_chair_review"


def _display(user):
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _require_reason(reason):
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise ValidationError(
            pgettext(
                _EVENT_CTX,
                "Səbəb ən azı {count} simvol olmalıdır — müəllim nəyi düzəltməli olduğunu bilməlidir.",
            ).format(count=MIN_REASON_LENGTH)
        )
    return reason


def record_event(submission, *, actor, actor_role, action, from_status, to_status, reason="", metadata=None):
    """Əlavə-only iz sətri. Heç vaxt yenilənmir/silinmir."""
    return QuestionSubmissionEvent.objects.create(
        submission=submission,
        organization=submission.organization,
        actor=actor if actor is not None and getattr(actor, "pk", None) else None,
        actor_label=_display(actor),
        actor_role=actor_role or "",
        action=action,
        from_status=from_status or "",
        to_status=to_status or "",
        reason=(reason or "").strip(),
        metadata=metadata or {},
    )


def _audit(submission, *, actor, action_label, from_status, to_status, reason=""):
    try:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=submission.organization,
            obj=submission,
            old_values={"status": from_status},
            new_values={"status": to_status},
            changes={"question_submission_stage": action_label},
            reason=str(reason or ""),
            resource_type="question_submission",
            resource_id=str(submission.pk),
            resource_repr=str(submission.title),
        )
    except Exception:  # noqa: BLE001 — audit əsas axını pozmur
        logger.warning("Question submission audit failed (%s).", action_label, exc_info=True)


def _invalidate_badges(user_ids, organization):
    try:
        from core.cache import invalidate_profile_badge_counts_cache

        org_id = organization.pk if organization is not None else None
        for user_id in set(user_ids):
            invalidate_profile_badge_counts_cache(user_id, org_id)
    except Exception:  # noqa: BLE001
        logger.warning("Question submission badge invalidation failed.", exc_info=True)


# ---------------------------------------------------------------------------
# Bildirişlər
# ---------------------------------------------------------------------------
def _notify(recipients, *, title, message, link, submission):
    try:
        from apps.notifications.public import create_notification

        for recipient in recipients:
            if recipient is None:
                continue
            create_notification(
                recipient=recipient,
                title=title,
                message=message,
                link=link,
                notification_type="exam",
                metadata={"question_submission_id": submission.id},
                organization=submission.organization,
            )
    except Exception:  # noqa: BLE001 — bildiriş əsas axını pozmur
        logger.warning("Question submission notification failed.", exc_info=True)


def _chair_review_link(submission):
    return reverse("exams:question_submission_chair_review", kwargs={"submission_id": submission.id})


def _teacher_link(submission):
    return reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})


def exam_center_members(organization):
    from apps.organizations.models import Membership

    return [
        membership.user
        for membership in Membership.objects.filter(
            organization=organization,
            # İmtahan Mərkəzi TƏK roldur (2026-09-06 birləşməsi, miqrasiya 0046);
            # köhnə ad hələ də sətirlərdə qala bilər — hər ikisi qəbul olunur.
            role__name__in=("exam_center_head", "exam_center"),
            is_active=True,
        ).select_related("user")
    ]


def notify_exam_center_ready(submission):
    """Kafedra təsdiqindən SONRA mərkəzə bildiriş (əvvəl deyil)."""
    recipients = [
        member for member in exam_center_members(submission.organization) if member.pk != submission.teacher_id
    ]
    _notify(
        recipients,
        title=pgettext(_EVENT_CTX, "Kafedra təsdiqli sual göndərişi"),
        message=pgettext(
            _EVENT_CTX,
            '{teacher} — "{title}" ({subject} · {group}, {count} sual) kafedra tərəfindən təsdiqləndi '
            "və İmtahan Mərkəzinə göndərildi.",
        ).format(
            teacher=_display(submission.teacher),
            title=submission.title,
            subject=submission.subject,
            group=submission.group_label,
            count=submission.question_count,
        ),
        link=reverse("exams:question_submission_review", kwargs={"submission_id": submission.id}),
        submission=submission,
    )
    _invalidate_badges([member.pk for member in recipients], submission.organization)


# ---------------------------------------------------------------------------
# Marşrut: müəllim → kafedra
# ---------------------------------------------------------------------------
@transaction.atomic
def route_submission_to_chair(submission, *, actor, resubmitted=False, groups=None):
    """Göndərişi kafedra mərhələsinə qoyur və təsdiqləyicilərə bildirir.

    ``groups`` verilməzsə göndərişin öz qrupları oxunur.  Kafedra müdiri
    tapılmasa DEKANLIĞA yönləndirilir (``routed_to_dean=True``).
    """
    from_status = submission.status
    if groups is None:
        groups = list(submission.student_groups.all()) or (
            [submission.student_group] if submission.student_group else []
        )
    chair_unit = resolve_submission_chair_unit(
        organization=submission.organization,
        teacher=submission.teacher,
        groups=groups,
    )
    targets, routed_to_dean = chair_route_targets(submission.organization, chair_unit)

    submission.chair_unit = chair_unit
    submission.routed_to_dean = routed_to_dean
    submission.status = QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR
    submission.chair_reviewer = None
    submission.chair_reviewed_at = None
    submission.chair_decision = ""
    submission.chair_note = ""
    submission.save(
        update_fields=[
            "chair_unit",
            "routed_to_dean",
            "status",
            "chair_reviewer",
            "chair_reviewed_at",
            "chair_decision",
            "chair_note",
            "updated_at",
        ]
    )

    action = (
        QuestionSubmissionEvent.ACTION_RESUBMITTED_TO_CHAIR
        if resubmitted
        else QuestionSubmissionEvent.ACTION_SUBMITTED_TO_CHAIR
    )
    record_event(
        submission,
        actor=actor,
        actor_role="teacher",
        action=action,
        from_status=from_status,
        to_status=submission.status,
        metadata={
            # UUID JSON-a birbaşa yazılmır — sətrə çevrilir (JSONField tələsi).
            "chair_unit_id": str(chair_unit.pk) if chair_unit is not None else None,
            "chair_unit_name": getattr(chair_unit, "name", ""),
            "routed_to_dean": routed_to_dean,
            "reviewer_count": len(targets),
        },
    )
    _audit(
        submission,
        actor=actor,
        action_label=action,
        from_status=from_status,
        to_status=submission.status,
    )

    recipients = [membership.user for membership in targets]
    if routed_to_dean:
        message = pgettext(
            _EVENT_CTX,
            '{teacher} "{title}" sual dəstini təsdiqə göndərdi. Kafedra müdiri təyin edilmədiyi üçün '
            "təsdiq DEKANLIĞA yönləndirildi ({subject} · {group}, {count} sual).",
        )
    else:
        message = pgettext(
            _EVENT_CTX,
            '{teacher} "{title}" sual dəstini kafedra təsdiqinə göndərdi ({subject} · {group}, {count} sual).',
        )
    _notify(
        recipients,
        title=pgettext(_EVENT_CTX, "Sual dəsti kafedra təsdiqini gözləyir"),
        message=message.format(
            teacher=_display(submission.teacher),
            title=submission.title,
            subject=submission.subject,
            group=submission.group_label,
            count=submission.question_count,
        ),
        link=_chair_review_link(submission),
        submission=submission,
    )
    _invalidate_badges([user.pk for user in recipients], submission.organization)
    return submission


# ---------------------------------------------------------------------------
# Kafedra qərarları
# ---------------------------------------------------------------------------
def ensure_can_chair_review(user, submission):
    if not can_review_submission_as_chair(user, submission):
        raise PermissionDenied(pgettext("exams.service.access.permission", "question_submission_chair_review_denied"))


def _ensure_at_chair(submission):
    if not submission.is_at_chair:
        raise ValidationError(
            pgettext(_EVENT_CTX, "Bu göndəriş artıq kafedra mərhələsində deyil — qərar verilə bilməz.")
        )


def _decide(submission, *, actor, decision, status, action, reason="", actor_role="chair_head"):
    submission = QuestionSubmission.objects.select_for_update(of=("self",)).get(pk=submission.pk)
    _ensure_at_chair(submission)
    from_status = submission.status
    submission.status = status
    submission.chair_reviewer = actor
    submission.chair_reviewed_at = timezone.now()
    submission.chair_decision = decision
    submission.chair_note = (reason or "").strip()
    update_fields = [
        "status",
        "chair_reviewer",
        "chair_reviewed_at",
        "chair_decision",
        "chair_note",
        "updated_at",
    ]
    if status == QuestionSubmission.STATUS_CHAIR_APPROVED:
        submission.reached_center_at = timezone.now()
        update_fields.append("reached_center_at")
    submission.save(update_fields=update_fields)
    record_event(
        submission,
        actor=actor,
        actor_role=actor_role,
        action=action,
        from_status=from_status,
        to_status=status,
        reason=reason,
        metadata={"chair_unit_id": str(submission.chair_unit_id) if submission.chair_unit_id else None},
    )
    _audit(
        submission,
        actor=actor,
        action_label=action,
        from_status=from_status,
        to_status=status,
        reason=reason,
    )
    return submission


def _actor_role_label(submission):
    return "dean" if submission.routed_to_dean else "chair_head"


@transaction.atomic
def chair_approve(submission, *, actor, note=""):
    """Kafedra təsdiqi → göndəriş İMTAHAN MƏRKƏZİNƏ çatır."""
    ensure_can_chair_review(actor, submission)
    submission = _decide(
        submission,
        actor=actor,
        decision=QuestionSubmission.CHAIR_DECISION_APPROVED,
        status=QuestionSubmission.STATUS_CHAIR_APPROVED,
        action=QuestionSubmissionEvent.ACTION_CHAIR_APPROVED,
        reason=(note or "").strip(),
        actor_role=_actor_role_label(submission),
    )
    _notify(
        [submission.teacher],
        title=pgettext(_EVENT_CTX, "Kafedra sual dəstinizi təsdiqlədi"),
        message=pgettext(
            _EVENT_CTX,
            '"{title}" sual dəstiniz kafedra tərəfindən təsdiqləndi və İmtahan Mərkəzinə göndərildi.',
        ).format(title=submission.title),
        link=_teacher_link(submission),
        submission=submission,
    )
    notify_exam_center_ready(submission)
    _invalidate_badges([actor.pk, submission.teacher_id], submission.organization)
    return submission


@transaction.atomic
def chair_request_revision(submission, *, actor, reason):
    """Kafedra düzəliş istəyir → müəllim redaktə edib YENİDƏN kafedraya göndərir."""
    ensure_can_chair_review(actor, submission)
    reason = _require_reason(reason)
    submission = _decide(
        submission,
        actor=actor,
        decision=QuestionSubmission.CHAIR_DECISION_REVISION,
        status=QuestionSubmission.STATUS_CHAIR_REVISION,
        action=QuestionSubmissionEvent.ACTION_CHAIR_REVISION,
        reason=reason,
        actor_role=_actor_role_label(submission),
    )
    _notify(
        [submission.teacher],
        title=pgettext(_EVENT_CTX, "Kafedra düzəliş istədi"),
        message=pgettext(
            _EVENT_CTX,
            '"{title}" sual dəstiniz kafedra tərəfindən düzəliş üçün qaytarıldı: {reason}',
        ).format(title=submission.title, reason=reason),
        link=_teacher_link(submission),
        submission=submission,
    )
    _invalidate_badges([actor.pk, submission.teacher_id], submission.organization)
    return submission


@transaction.atomic
def chair_reject(submission, *, actor, reason):
    """Kafedra rədd edir → göndəriş mərkəzə HEÇ VAXT çatmır."""
    ensure_can_chair_review(actor, submission)
    reason = _require_reason(reason)
    submission = _decide(
        submission,
        actor=actor,
        decision=QuestionSubmission.CHAIR_DECISION_REJECTED,
        status=QuestionSubmission.STATUS_REJECTED,
        action=QuestionSubmissionEvent.ACTION_CHAIR_REJECTED,
        reason=reason,
        actor_role=_actor_role_label(submission),
    )
    _notify(
        [submission.teacher],
        title=pgettext(_EVENT_CTX, "Kafedra sual dəstini rədd etdi"),
        message=pgettext(
            _EVENT_CTX,
            '"{title}" sual dəstiniz kafedra tərəfindən rədd edildi: {reason}',
        ).format(title=submission.title, reason=reason),
        link=_teacher_link(submission),
        submission=submission,
    )
    _invalidate_badges([actor.pk, submission.teacher_id], submission.organization)
    return submission


# ---------------------------------------------------------------------------
# Növbə
# ---------------------------------------------------------------------------
def chair_queue_queryset(user, organization):
    """Aktorun görə bildiyi kafedra göndərişləri (əhatə yoxdursa BOŞ)."""
    if organization is None:
        return QuestionSubmission.objects.none()
    condition = chair_queue_filter(user, organization)
    if condition is None:
        return QuestionSubmission.objects.none()
    return QuestionSubmission.objects.filter(organization=organization).filter(condition)


def pending_chair_review_count(user, organization) -> int:
    return chair_queue_queryset(user, organization).filter(status=QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR).count()


__all__ = [
    "MIN_REASON_LENGTH",
    "chair_approve",
    "chair_queue_queryset",
    "chair_reject",
    "chair_request_revision",
    "ensure_can_chair_review",
    "exam_center_members",
    "notify_exam_center_ready",
    "pending_chair_review_count",
    "record_event",
    "route_submission_to_chair",
]
