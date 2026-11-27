"""TOPLU in-app bildirişlər (``apps.notifications.public``).

* tələbələr: qovluq təyin olundu, yeni tapşırıq dərc olundu — auditoriyaya TƏK
  bulk insert; qaytarıldı / qəbul edildi / yoxlanıldı / rədd edildi — eyni
  (hadisə, tapşırıq, bal) qrupu bir bulk insert;
* müəllim: yeni göndərişlər XÜLASƏSİ (digest) — hər göndərişə ayrıca bildiriş
  YOX; müəllimə ``DIGEST_INTERVAL`` ərzində ən çox bir bildiriş gedir, qalanları
  növbəti göndərişdə və ya dövri tapşırıqda (``send_submission_digests``) toplanır.

Bildiriş nasazlığı domen əməliyyatını HEÇ VAXT geri qaytarmır: hamısı
``transaction.on_commit`` + try/except + logger (syllabus bildirişləri ilə eyni nizam).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import SECTION_REVIEW, SECTION_STUDENT, FolderStatus, SubmissionStatus, TaskKind
from ..errors import display_number
from . import lookups, selfwork_rule
from .locks import advisory_lock

logger = logging.getLogger(__name__)

_CTX = "subject_folder.notify"
EVENT_PREFIX = "subject_folder."


def digest_interval() -> timedelta:
    minutes = getattr(settings, "SUBJECT_FOLDER_DIGEST_MINUTES", 15)
    try:
        return timedelta(minutes=max(1, int(minutes)))
    except (TypeError, ValueError):
        return timedelta(minutes=15)


def profile_link(section: str, **params) -> str:
    """``/accounts/profile/?section=<slug>&sf_…`` — UI agenti bölməni bu slug ilə qeyd edir."""
    try:
        base = reverse("accounts:profile")
    except NoReverseMatch:  # pragma: no cover — accounts URL-ləri yüklənməyib
        base = "/accounts/profile/"
    query = {"section": section, **{key: str(value) for key, value in params.items() if value}}
    return f"{base}?{urlencode(query)}"


def _dispatch(recipients, *, title, message, link, organization_id, metadata, kind="assignment") -> None:
    users = [user for user in dict.fromkeys(recipients) if user is not None]
    if not users:
        return

    def _send():
        try:
            from apps.notifications.public import create_notification_for_users

            create_notification_for_users(
                recipients=users,
                title=str(title)[:255],
                message=str(message),
                link=link,
                notification_type=kind,
                organization=organization_id,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover — bildiriş iş axınını bloklamır
            logger.exception("subject_folder notification failed (%s)", metadata.get("event"))

    transaction.on_commit(_send)


def _audience_users(offering_ids) -> list:
    rows = lookups.audience_enrollments(list(offering_ids)).select_related("student").order_by("student_id")
    return [row.student for row in rows]


def folder_assigned(assignment) -> None:
    folder = assignment.folder
    _dispatch(
        _audience_users([assignment.offering_id]),
        title=pgettext(_CTX, "Yeni fənn qovluğu: %(subject)s") % {"subject": folder.subject.name},
        message=pgettext(_CTX, "«%(folder)s» — tədris materialları və tapşırıqlar sizin üçün açıqdır.")
        % {"folder": folder.title},
        link=profile_link(SECTION_STUDENT, sf_folder=folder.pk),
        organization_id=folder.organization_id,
        metadata={"event": EVENT_PREFIX + "assigned", "folder_id": str(folder.pk)},
        kind="course",
    )


def task_published(task) -> None:
    folder = task.folder
    if folder.status != FolderStatus.ACTIVE:
        return
    offering_ids = list(folder.assignments.filter(is_active=True).values_list("offering_id", flat=True))
    if task.kind == TaskKind.SELFWORK:  # sahib 2026-10-10: sərbəst iş ləğv olunan qrupa «Yeni sərbəst iş» getmir
        offering_ids = sorted(selfwork_rule.active_offering_ids(offering_ids), key=str)
    if not offering_ids:
        return
    label = (
        pgettext(_CTX, "Yeni sərbəst iş: %(title)s")
        if task.kind == TaskKind.SELFWORK
        else pgettext(_CTX, "Yeni ev tapşırığı: %(title)s")
    )
    _dispatch(
        _audience_users(offering_ids),
        title=label % {"title": task.title},
        message=folder.subject.name,
        link=profile_link(SECTION_STUDENT, sf_folder=folder.pk, sf_task=task.pk),
        organization_id=folder.organization_id,
        metadata={"event": EVENT_PREFIX + "task_published", "task_id": str(task.pk), "folder_id": str(folder.pk)},
    )


def _outcome_texts(status, task, points):
    title = task.title
    if status == SubmissionStatus.RETURNED:
        return pgettext(_CTX, "İşiniz yenidən işləməyə qaytarıldı: %(task)s") % {"task": title}, pgettext(
            _CTX, "Müəllimin rəyini oxuyun və işi yenidən göndərin."
        )
    if status == SubmissionStatus.ACCEPTED:
        head = pgettext(_CTX, "Sərbəst iş qəbul edildi: %(task)s") % {"task": title}
        if points is None:
            return head, pgettext(_CTX, "Bal jurnala köçürülür.")
        body = pgettext(_CTX, "Bal: %(points)s / %(max)s — jurnala köçürülür.") % {
            "points": _fmt(points),
            "max": _fmt(task.max_points),
        }
        return head, body
    if status == SubmissionStatus.CHECKED:
        return pgettext(_CTX, "Ev tapşırığı yoxlanıldı: %(task)s") % {"task": title}, ""
    return pgettext(_CTX, "İşiniz rədd edildi: %(task)s") % {"task": title}, pgettext(
        _CTX, "Səbəb və rəy tapşırıq səhifəsindədir."
    )


def _fmt(value):
    return display_number(value) if value is not None else ""


def review_outcomes(submissions) -> None:
    """Baxış nəticələri — (status, tapşırıq, bal) üzrə qruplaşdırılmış TOPLU bildirişlər."""
    groups = defaultdict(list)
    for submission in submissions:
        points = submission.points if submission.status == SubmissionStatus.ACCEPTED else None
        groups[(submission.status, submission.task_id, points)].append(submission)
    for (status, _task_id, points), rows in groups.items():
        first = rows[0]
        task = first.task
        # Qrupda bal eynidir; qrup çox tələbəlidirsə mətn yenə dəqiqdir.
        title, message = _outcome_texts(status, task, points)
        _dispatch(
            [row.student for row in rows],
            title=title,
            message=message,
            link=profile_link(SECTION_STUDENT, sf_folder=task.folder_id, sf_task=task.pk),
            organization_id=first.organization_id,
            metadata={
                "event": EVENT_PREFIX + str(status),
                "task_id": str(task.pk),
                "submission_ids": [str(row.pk) for row in rows][:50],
            },
            kind="grade",
        )


# ── Müəllimə yeni göndərişlər xülasəsi ─────────────────────────────────────


def _pending_digest_rows(organization_id=None, teacher_id=None):
    from ..models import Submission

    rows = Submission.objects.filter(
        status=SubmissionStatus.SUBMITTED, teacher_notified_at__isnull=True, is_current=True
    ).select_related("task")
    if organization_id is not None:
        rows = rows.filter(organization_id=organization_id)
    if teacher_id is not None:
        rows = rows.filter(_teacher_q(teacher_id))
    return rows


def _teacher_q(teacher_id) -> Q:
    return Q(assignment__offering__instructor_id=teacher_id) | Q(
        assignment__offering__instructor__isnull=True, task__folder__owner_id=teacher_id
    )


def _recipient_id(submission):
    return submission.assignment.offering.instructor_id or submission.task.folder.owner_id


def _send_digest(teacher, organization_id, rows) -> bool:
    from apps.notifications.public import create_notification_for_users

    from ..models import Submission

    counts = defaultdict(int)
    for row in rows:
        counts[row.task.title] += 1
    total = sum(counts.values())
    summary = " · ".join(f"{title} — {count}" for title, count in sorted(counts.items())[:8])
    created = create_notification_for_users(
        recipients=[teacher],
        title=pgettext(_CTX, "Yoxlanılmalı yeni işlər: %(count)s") % {"count": total},
        message=summary,
        link=profile_link(SECTION_REVIEW),
        organization=rows[0].organization,
        notification_type="assignment",
        metadata={"event": EVENT_PREFIX + "digest", "count": total},
    )
    if not created:
        return False
    Submission.objects.filter(organization_id=organization_id, pk__in=[row.pk for row in rows]).update(
        teacher_notified_at=timezone.now()
    )
    return True


def pending_digest_recipients(organization_id=None, teacher_id=None):
    rows = _pending_digest_rows(organization_id, teacher_id).annotate(
        recipient_id=Coalesce("assignment__offering__instructor_id", "task__folder__owner_id")
    )
    return list(
        rows.exclude(recipient_id=None)
        .order_by("organization_id", "recipient_id")
        .values_list("organization_id", "recipient_id")
        .distinct()
    )


@transaction.atomic
def _deliver_digest(organization_id, teacher_id, *, force):
    from ..models import Submission

    advisory_lock("sf", "digest", organization_id, teacher_id)
    if (
        not force
        and Submission.objects.filter(
            _teacher_q(teacher_id),
            organization_id=organization_id,
            teacher_notified_at__gte=timezone.now() - digest_interval(),
        ).exists()
    ):
        return False
    teacher = get_user_model().objects.filter(pk=teacher_id, is_active=True).first()
    if teacher is None:
        return False
    rows = list(_pending_digest_rows(organization_id, teacher_id).select_for_update(of=("self",)))
    return bool(rows) and _send_digest(teacher, organization_id, rows)


def send_submission_digests(*, organization_id=None, teacher_id=None, force: bool = True) -> int:
    """Create one inbox entry per organization and teacher in the caller's visibility scope."""
    recipients = pending_digest_recipients(organization_id, teacher_id)
    return sum(_deliver_digest(org, teacher, force=force) for org, teacher in recipients)


@transaction.atomic
def deliver_pending_digest(organization_id, teacher_id, *, force=False):
    """Run a committed submission or a trusted worker candidate in its own tenant context."""
    from core.rls import apply_rls_request_context

    apply_rls_request_context(user_id=teacher_id, org_id=organization_id, local=True)
    return _deliver_digest(organization_id, teacher_id, force=force)


def run_pending_digests(*, force=False):
    """Deliver periodic or operator-requested digests independently for each tenant and recipient."""
    from core.rls import bypass_rls
    from core.rls_pooling import rls_worker_atomic

    # Discover keys only. Read submission content and write each inbox in its own tenant transaction.
    with rls_worker_atomic(), bypass_rls():
        recipients = pending_digest_recipients()
    sent = failed = 0
    for organization_id, teacher_id in recipients:
        try:
            sent += deliver_pending_digest(organization_id, teacher_id, force=force)
        except Exception as exc:
            # One unavailable inbox must not starve other tenants. Its rows remain pending for the next run.
            logger.error("subject_folder digest transaction failed (%s)", type(exc).__name__)
            failed += 1
    if failed:
        raise RuntimeError(f"Failed to commit {failed} subject folder digest(s)")
    return sent


def submission_received(submission) -> None:
    """Göndərişdən sonra (commit-də): müəllimə son intervalda xülasə getməyibsə indi göndər."""
    teacher_id = _recipient_id(submission)
    organization_id = submission.organization_id

    def _run():
        try:
            if teacher_id is not None:
                deliver_pending_digest(organization_id, teacher_id)
        except Exception:  # pragma: no cover — bildiriş göndərişi bloklamır
            logger.exception("subject_folder teacher digest failed")

    transaction.on_commit(_run)


__all__ = [
    "digest_interval",
    "folder_assigned",
    "profile_link",
    "review_outcomes",
    "send_submission_digests",
    "submission_received",
    "task_published",
]
