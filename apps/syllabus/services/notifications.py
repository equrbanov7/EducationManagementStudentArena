"""Sillabus iş axını keçidləri üçün in-app bildirişlər.

Hər keçiddən sonra (``workflow.py``, tranzaksiya commit olandan SONRA)
müvafiq tərəfə bildiriş gedir. Bildiriş nasazlığı keçidi HEÇ VAXT geri
qaytarmır — ``transaction.on_commit`` + try/except+logger konvensiyası
(bax ``apps/registrar/schedule_manage_actions.py::_schedule_notification``).

Modul sərhədi: ``apps.organizations``/``apps.notifications`` importu buradan
YALNIZ funksiya daxilində (lazy) edilir ki, ``scripts/module_deps.py --check``
YENİ DÖVRÜ aşkarlasa dərhal görünsün — heç bir tərəf syllabus-u geri idxal
etmir, ona görə dövr yaranmır (``scripts/module_deps.py`` yalnız YENİ dövrü/
core→apps kənarını gate edir, bax skriptin ``cmd_check``-i).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

logger = logging.getLogger(__name__)

_CTX = "syllabus.notify"

# metadata={"event": ...} üçün keçid adları state_machine.Transition ilə eynidir.
EVENT_SUBMIT = "syllabus_submit"
EVENT_START_REVIEW = "syllabus_start_review"
EVENT_APPROVE = "syllabus_approve"
EVENT_REVISION = "syllabus_request_revision"
EVENT_REJECT = "syllabus_reject"
EVENT_WITHDRAW = "syllabus_withdraw"

#: Kafedra müdiri təyin edilməyəndə dekana gedən bildirişin İZAH QEYDİ.
#: Səssiz düşmə OLMUR — amma dekan da bilir ki, qərar açarı onda deyil.
FALLBACK_NOTE = pgettext_lazy(
    _CTX,
    "Bu kafedra üçün kafedra müdiri təyin edilməyib, ona görə bildiriş dekanlığa göndərildi. "
    "Təsdiq kafedra müdirinin səlahiyyətindədir — zəhmət olmasa müdir təyin edin.",
)


def _detail_link(syllabus_id) -> str:
    return reverse("accounts:syllabus_detail", kwargs={"syllabus_id": syllabus_id})


def _dispatch(event: str, *, recipients, title: str, message: str, syllabus) -> None:
    """Alıcılar boş deyilsə, commit-dən sonra TƏK toplu bildiriş göndərir."""
    recipients = [user for user in dict.fromkeys(recipients) if user is not None]
    if not recipients:
        return

    organization = syllabus.organization
    link = _detail_link(syllabus.pk)
    metadata = {"event": event, "syllabus_id": str(syllabus.pk)}

    def _send() -> None:
        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification_for_users

            create_notification_for_users(
                recipients=recipients,
                title=title,
                message=message,
                link=link,
                notification_type=NotificationType.APPROVAL,
                organization=organization,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover — bildiriş iş axınını BLOKLAMIR
            logger.exception("syllabus workflow notification failed (event=%s)", event)

    transaction.on_commit(_send)


def _chair_head_recipients(syllabus) -> list:
    if not syllabus.chair_unit_id:
        return []
    from apps.organizations.public import chair_head_memberships_for_unit

    return [
        membership.user for membership in chair_head_memberships_for_unit(syllabus.organization, syllabus.chair_unit)
    ]


def _dean_recipients(syllabus) -> list:
    if not syllabus.chair_unit_id:
        return []
    from apps.organizations.public import dean_memberships_for_unit

    return [membership.user for membership in dean_memberships_for_unit(syllabus.organization, syllabus.chair_unit)]


def notify_submitted(version) -> None:
    """SUBMIT → kafedra müdirləri; MÜDİR YOXDURSA dekanlar QEYDLƏ xəbərdar olunur.

    Sahibin qərarı ilə (2026-09-03) təsdiq kafedra müdirinindir, ona görə dekana
    gedən bildiriş «sizin qərarınızı gözləyir» kimi oxunmamalıdır — mesaja
    dekanın NİYƏ xəbər aldığı və nə etməli olduğu yazılır.  Alıcı siyahısı BOŞ
    QALMIR: heç kim tapılmasa belə hadisə səssizcə itmir, jurnala düşür.
    """
    syllabus = version.syllabus
    recipients = _chair_head_recipients(syllabus)
    message = version.label
    if not recipients:
        recipients = _dean_recipients(syllabus)
        if recipients:
            message = "%s — %s" % (version.label, str(FALLBACK_NOTE))
        else:
            logger.warning(
                "syllabus submitted but no chair head or dean covers chair_unit=%s (syllabus=%s)",
                syllabus.chair_unit_id,
                syllabus.pk,
            )
    title = pgettext(_CTX, "Sillabus təsdiqə göndərildi: %(subject)s") % {"subject": syllabus.subject.name}
    _dispatch(EVENT_SUBMIT, recipients=recipients, title=title, message=message, syllabus=syllabus)


def notify_review_opened(version) -> None:
    """START_REVIEW → müəllif xəbərdar olunur (kafedra baxışa götürüb)."""
    syllabus = version.syllabus
    title = pgettext(_CTX, "Sillabusunuz baxışa götürüldü")
    _dispatch(
        EVENT_START_REVIEW,
        recipients=[syllabus.author],
        title=title,
        message=syllabus.subject.name,
        syllabus=syllabus,
    )


def notify_approved(version) -> None:
    """APPROVE → müəllif xəbərdar olunur."""
    syllabus = version.syllabus
    title = pgettext(_CTX, "Sillabus təsdiqləndi")
    _dispatch(
        EVENT_APPROVE,
        recipients=[syllabus.author],
        title=title,
        message=syllabus.subject.name,
        syllabus=syllabus,
    )


def notify_revision_requested(version) -> None:
    """REQUEST_REVISION → müəllif səbəblə xəbərdar olunur."""
    syllabus = version.syllabus
    title = pgettext(_CTX, "Sillabus düzəliş üçün qaytarıldı: %(reason)s") % {"reason": version.decision_reason}
    _dispatch(
        EVENT_REVISION,
        recipients=[syllabus.author],
        title=title,
        message=syllabus.subject.name,
        syllabus=syllabus,
    )


def notify_rejected(version) -> None:
    """REJECT → müəllif səbəblə xəbərdar olunur."""
    syllabus = version.syllabus
    title = pgettext(_CTX, "Sillabus rədd edildi: %(reason)s") % {"reason": version.decision_reason}
    _dispatch(
        EVENT_REJECT,
        recipients=[syllabus.author],
        title=title,
        message=syllabus.subject.name,
        syllabus=syllabus,
    )


def notify_withdrawn(version, *, reviewer) -> None:
    """WITHDRAW → baxışı açmış rəyçi(lər) xəbərdar olunur.

    ``reviewer`` çağıran tərəfindən keçiddən ƏVVƏL tutulmalıdır — ``withdraw``
    keçidi ``SyllabusVersion.reviewer``-i ``None``-a yazır, ona görə burada
    versiyanın ÖZÜNDƏN yenidən oxumaq artıq boş qayıdar.
    """
    if reviewer is None:
        return
    syllabus = version.syllabus
    title = pgettext(_CTX, "Sillabus geri çağırıldı: %(subject)s") % {"subject": syllabus.subject.name}
    _dispatch(EVENT_WITHDRAW, recipients=[reviewer], title=title, message="", syllabus=syllabus)


__all__ = [
    "EVENT_APPROVE",
    "EVENT_REJECT",
    "EVENT_REVISION",
    "EVENT_START_REVIEW",
    "EVENT_SUBMIT",
    "EVENT_WITHDRAW",
    "FALLBACK_NOTE",
    "notify_approved",
    "notify_rejected",
    "notify_review_opened",
    "notify_revision_requested",
    "notify_submitted",
    "notify_withdrawn",
]
