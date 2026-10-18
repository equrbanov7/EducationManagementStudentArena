"""25% / alt qrup müraciəti bildirişləri — BEST-EFFORT (xəta qərar tranzaksiyasını sındırmır).

* Tələbə HƏR status dəyişikliyində bildiriş alır (link: kabinetin «25% və alt qrup» bölməsi).
* 2026-10-19: «Ödənişin qaytarılması qərarı» — tələbəyə və ``retake.payment_verify`` daşıyanlara (növbə «Qaytarılacaq
  ödənişlər»), «Qaytarıldı» — tələbəyə (:func:`notify_refund`).
* Növbəyə düşən müraciət haqqında açar daşıyan heyətə xəbər verilir: qəbz yüklənəndə
  ``retake.payment_verify``, ödəniş təsdiqlənəndə / alt qrup müraciəti gələndə ``retake.manage``.
  Alıcılar rol ADI ilə yox, açarı AÇIQ yazılmış aktiv rollarla tapılır (wildcard ``*`` rollar — rektor və
  s. — QƏSDƏN daxil edilmir, hər müraciətdə spam almasınlar; ``appeals.services.notify`` ilə eyni qayda).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from .models import RetakeKind, RetakeStatus

logger = logging.getLogger(__name__)

_CTX = "registrar.retake.notification"

STUDENT_SECTION = "my-retakes"
DESK_SECTION = "retake-desk"


def _section_link(section: str) -> str:
    return f"{reverse('accounts:profile')}?section={section}"


def _messages(application) -> tuple[str, str]:
    subject = getattr(application.subject, "name", "") or ""
    status = application.status
    titles = {
        RetakeStatus.SUBMITTED: pgettext(_CTX, "Müraciətiniz qəbul edildi"),
        RetakeStatus.PAYMENT_PENDING_REVIEW: pgettext(_CTX, "Qəbz yoxlamaya göndərildi"),
        RetakeStatus.PAYMENT_REJECTED: pgettext(_CTX, "Ödəniş qəbzi rədd edildi"),
        RetakeStatus.PAYMENT_VERIFIED: pgettext(_CTX, "Ödənişiniz təsdiqləndi"),
        RetakeStatus.ADMITTED: (
            pgettext(_CTX, "Alt qrup müraciətiniz təsdiqləndi")
            if application.kind == RetakeKind.SUBGROUP
            else pgettext(_CTX, "25% təkrar imtahana buraxıldınız")
        ),
        RetakeStatus.EXAM_GRANTED: pgettext(_CTX, "Təkrar imtahan cəhdi açıldı"),
        RetakeStatus.COMPLETED: (
            pgettext(_CTX, "Alt qrupa yerləşdirildiniz")
            if application.kind == RetakeKind.SUBGROUP
            else pgettext(_CTX, "25% təkrar imtahanın nəticəsi yazıldı")
        ),
        RetakeStatus.REJECTED: pgettext(_CTX, "Müraciətiniz rədd edildi"),
        RetakeStatus.WITHDRAWN: pgettext(_CTX, "Müraciət geri götürüldü"),
    }
    title = titles.get(status, pgettext(_CTX, "Müraciətinizin vəziyyəti dəyişdi"))
    message = pgettext(_CTX, '"{subject}" — {kind}: {status}.').format(
        subject=subject, kind=RetakeKind(application.kind).label, status=RetakeStatus(status).label
    )
    if status == RetakeStatus.COMPLETED and application.result_score is not None:
        message += " " + pgettext(_CTX, "Bal: {score}.").format(score=format(application.result_score.normalize(), "f"))
    return title, message


def notify_student(application, *, note: str = "") -> None:
    def _send():
        try:
            from apps.notifications.public import create_notification

            title, message = _messages(application)
            if note:
                message = f"{message} {note}"[:2000]
            create_notification(
                recipient=application.student,
                title=title,
                message=message,
                link=_section_link(STUDENT_SECTION),
                notification_type="application",
                metadata={"retake_application_id": str(application.pk), "status": application.status},
                organization=application.organization,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Retake student notification failed.", exc_info=True)

    transaction.on_commit(_send)


def _covers(unit, groups) -> bool:
    """UNIT rolunun ``scope_unit``-i tələbənin qrupunu (və ya kəsr açılışın qrupunu) əhatə edirmi."""
    if unit is None:
        return False
    path = getattr(unit, "path", "") or ""
    for group in groups:
        if group is None:
            continue
        if group.pk == unit.pk or (path and (getattr(group, "path", "") or "").startswith(f"{path}/")):
            return True
    return False


def _key_holders(application, key) -> list:
    """Açarı AÇIQ yazılmış aktiv üzvlər — rəy 2026-10-18 (LOW-8): UNIT rolu yalnız əhatəsindəki tələbəyə görə;
    ORGANIZATION rolu hamısını alır."""
    from django.apps import apps as django_apps

    from core.constants import RoleScopeType

    membership_model = django_apps.get_model("organizations", "Membership")
    rows = (
        membership_model.objects.select_related("user", "role", "scope_unit")
        .filter(organization_id=application.organization_id, is_active=True, role__is_active=True, user__is_active=True)
        .order_by("user_id")
    )
    groups = [application.student_group, getattr(getattr(application, "enrollment", None), "offering", None)]
    groups = [groups[0], getattr(groups[1], "group", None)]
    seen, users = set(), []
    for membership in rows:
        if membership.user_id in seen or membership.user_id == application.student_id:
            continue
        if key not in list(getattr(membership.role, "permissions", None) or []):
            continue
        scope_type = getattr(membership.role, "scope_type", "")
        if scope_type == RoleScopeType.UNIT and not _covers(membership.scope_unit, groups):
            continue
        if scope_type not in (RoleScopeType.UNIT, RoleScopeType.ORGANIZATION):
            continue
        seen.add(membership.user_id)
        users.append(membership.user)
    return users


def notify_staff_queue(application, key: str) -> None:
    def _send():
        try:
            from apps.notifications.public import create_notification_for_users

            recipients = _key_holders(application, key)
            if not recipients:
                return
            student = application.student
            create_notification_for_users(
                recipients=recipients,
                title=pgettext(_CTX, "Yeni 25% / alt qrup müraciəti növbədədir"),
                message=pgettext(_CTX, '{student} — "{subject}": {status}.').format(
                    student=(student.get_full_name() or "").strip() or student.username,
                    subject=getattr(application.subject, "name", ""),
                    status=RetakeStatus(application.status).label,
                ),
                link=_section_link(DESK_SECTION),
                notification_type="application",
                metadata={"retake_application_id": str(application.pk)},
                organization=application.organization,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Retake staff notification failed.", exc_info=True)

    transaction.on_commit(_send)


def _refund_text(application, stage: str) -> tuple[str, str]:
    subject = getattr(application.subject, "name", "") or ""
    amount = format(application.refund_amount.normalize(), "f") if application.refund_amount is not None else "—"
    if stage == "refunded":
        return (
            pgettext(_CTX, "Ödəniş qaytarıldı"),
            pgettext(_CTX, '"{subject}" — 25% ödənişi qaytarıldı: {amount} AZN ({date}).').format(
                subject=subject,
                amount=amount,
                date=application.refunded_on.strftime("%d.%m.%Y") if application.refunded_on else "—",
            ),
        )
    return (
        pgettext(_CTX, "Ödənişin qaytarılması qərarı verildi"),
        pgettext(
            _CTX, '"{subject}" — 25% ödənişinin qaytarılması qərarı: {amount} AZN. Mühasibatlıq icra edəcək.'
        ).format(subject=subject, amount=amount),
    )


def notify_refund(application, *, stage: str, staff_key: str = "") -> None:
    """2026-10-19: qaytarılma qərarı / icrası — tələbəyə və (qərarda) Mühasibatlığa; BEST-EFFORT, commit-dən sonra."""

    def _send():
        try:
            from apps.notifications.public import create_notification, create_notification_for_users

            title, message = _refund_text(application, stage)
            metadata = {"retake_application_id": str(application.pk), "refund_state": application.refund_state}
            create_notification(
                recipient=application.student,
                title=title,
                message=message,
                link=_section_link(STUDENT_SECTION),
                notification_type="application",
                metadata=metadata,
                organization=application.organization,
            )
            recipients = _key_holders(application, staff_key) if staff_key else []
            if recipients:
                student = application.student
                create_notification_for_users(
                    recipients=recipients,
                    title=pgettext(_CTX, "Qaytarılacaq ödəniş növbədədir"),
                    message=pgettext(_CTX, "{student} — {message}").format(
                        student=(student.get_full_name() or "").strip() or student.username, message=message
                    ),
                    link=f"{_section_link(DESK_SECTION)}&rt_tab=refunds",
                    notification_type="application",
                    metadata=metadata,
                    organization=application.organization,
                )
        except Exception:  # noqa: BLE001
            logger.warning("Retake refund notification failed.", exc_info=True)

    transaction.on_commit(_send)


__all__ = ["DESK_SECTION", "STUDENT_SECTION", "notify_refund", "notify_staff_queue", "notify_student"]
