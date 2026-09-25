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
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import SECTION_REVIEW, SECTION_STUDENT, FolderStatus, SubmissionStatus, TaskKind
from ..errors import display_number
from . import lookups

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
    ).select_related("task", "task__folder", "assignment__offering", "assignment__offering__instructor")
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


def _send_digest(teacher, rows) -> None:
    from ..models import Submission

    counts = defaultdict(int)
    for row in rows:
        counts[row.task.title] += 1
    total = sum(counts.values())
    summary = " · ".join(f"{title} — {count}" for title, count in sorted(counts.items())[:8])
    _dispatch(
        [teacher],
        title=pgettext(_CTX, "Yoxlanılmalı yeni işlər: %(count)s") % {"count": total},
        message=summary,
        link=profile_link(SECTION_REVIEW),
        organization_id=rows[0].organization_id,
        metadata={"event": EVENT_PREFIX + "digest", "count": total},
    )
    Submission.objects.filter(pk__in=[row.pk for row in rows]).update(teacher_notified_at=timezone.now())


def send_submission_digests(*, organization_id=None, teacher_id=None, force: bool = True) -> int:
    """Gözləyən göndərişləri müəllimlər üzrə bir bildirişdə toplayır → göndərilən bildiriş sayı.

    ``force=False`` — müəllimə son ``digest_interval()`` ərzində xülasə gedibsə ötürülür.
    """
    user_model = get_user_model()
    grouped = defaultdict(list)
    for row in _pending_digest_rows(organization_id, teacher_id):
        grouped[_recipient_id(row)].append(row)
    sent = 0
    cutoff = timezone.now() - digest_interval()
    from ..models import Submission

    for recipient_id, rows in grouped.items():
        if recipient_id is None:
            continue
        if not force and Submission.objects.filter(_teacher_q(recipient_id), teacher_notified_at__gte=cutoff).exists():
            continue
        teacher = user_model.objects.filter(pk=recipient_id, is_active=True).first()
        if teacher is None:
            continue
        _send_digest(teacher, rows)
        sent += 1
    return sent


def submission_received(submission) -> None:
    """Göndərişdən sonra (commit-də): müəllimə son intervalda xülasə getməyibsə indi göndər."""
    teacher_id = _recipient_id(submission)
    organization_id = submission.organization_id

    def _run():
        try:
            send_submission_digests(organization_id=organization_id, teacher_id=teacher_id, force=False)
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
