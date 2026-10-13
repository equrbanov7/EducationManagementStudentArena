"""Apellyasiya bildirişləri — alıcıların tapılması + müəllim bildirişləri (2026-10-13, gecə).

Sahib: «apellyasiyaya verilmə, cavabın düzəldilməsi…» — qərar balı dəyişəndə təkcə tələbə yox,
fənnin MÜƏLLİMİ də bilməlidir:

* final → jurnal balı avtomatik yenilənir (``journal_sync``), müəllimə məlumat verilir;
* midterm → midterm balını jurnala müəllim özü yazır (sahibin qərarı, ``journal_sync`` docstring-i),
  ona görə bildiriş «jurnalda midterm balını yeniləyin» deyir.

İmtahan mərkəzinin alıcıları rol ADI ilə yox, ``appeal.respond`` AÇARI ilə tapılır (rol auditi
2026-10-13 B1 qaydası); açarlı heç kim yoxdursa köhnə rol adlarına düşülür ki, bildiriş itməsin.

Bütün funksiyalar BEST-EFFORT-dur: bildiriş xətası qərar tranzaksiyasını heç vaxt sındırmır.
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.urls import reverse
from django.utils.translation import pgettext

from apps.appeals.constants import PERM_APPEAL_RESPOND

logger = logging.getLogger(__name__)

#: Açar tapılmayanda geri düşmə (köhnə davranış) — İmtahan Mərkəzi TƏK roldur (miqrasiya 0046).
_LEGACY_EXAM_CENTER_ROLES = ("exam_center_head", "exam_center")


def _active_memberships(organization):
    membership_model = django_apps.get_model("organizations", "Membership")
    return (
        membership_model.objects.select_related("user", "role")
        .filter(organization=organization, is_active=True, role__is_active=True, user__is_active=True)
        .order_by("user_id")
    )


def exam_center_recipients(appeal):
    """Apellyasiyaya cavab verə bilən (``appeal.respond`` açarı AÇIQ yazılmış) aktiv üzvlər.

    Wildcard (``*``) rollar QƏSDƏN daxil edilmir — rektor/sahib hər müraciətdə spam almasın."""
    if not getattr(appeal, "organization_id", None):
        return []
    memberships = list(_active_memberships(appeal.organization).exclude(user_id=appeal.student_id))
    seen, recipients = set(), []
    for membership in memberships:
        permissions = list(getattr(membership.role, "permissions", None) or [])
        if PERM_APPEAL_RESPOND in permissions and membership.user_id not in seen:
            seen.add(membership.user_id)
            recipients.append(membership.user)
    if recipients:
        return recipients
    for membership in memberships:
        if membership.role.name in _LEGACY_EXAM_CENTER_ROLES and membership.user_id not in seen:
            seen.add(membership.user_id)
            recipients.append(membership.user)
    return recipients


def teacher_recipients(exam, student_ids):
    """İmtahanın müəllifi + tələbələrin həmin fənn üzrə açılışlarının müəllimləri (tələbələr çıxmaqla)."""
    student_ids = {sid for sid in student_ids if sid}
    user_ids = set()
    author_id = getattr(exam, "author_id", None)
    if author_id:
        user_ids.add(author_id)
    subject_id = getattr(exam, "subject_id", None)
    if subject_id and student_ids:
        try:
            enrollment_model = django_apps.get_model("registrar", "Enrollment")
            user_ids.update(
                enrollment_model.objects.filter(
                    student_id__in=student_ids,
                    offering__subject_id=subject_id,
                    offering__organization_id=exam.organization_id,
                    offering__instructor_id__isnull=False,
                )
                .values_list("offering__instructor_id", flat=True)
                .distinct()
            )
        except LookupError:  # registrar quraşdırılmayıb
            pass
    user_ids -= student_ids
    if not user_ids:
        return []
    from django.contrib.auth import get_user_model

    return list(get_user_model().objects.filter(pk__in=user_ids, is_active=True).order_by("pk"))


def _signed_points(value):
    """``Decimal('1.00')`` → «+1», ``-0.5`` → «-0.5» (bildiriş mətni üçün)."""
    from decimal import Decimal

    number = Decimal(str(value)).normalize()
    text = format(number, "f")
    return text if text.startswith("-") else f"+{text}"


def _is_midterm(exam):
    return str(getattr(exam, "exam_type_extended", "") or "") == "midterm"


def _journal_hint(exam):
    if _is_midterm(exam):
        return pgettext(
            "appeals.notification",
            "Midterm balını elektron jurnalda özünüz yeniləyin (midterm jurnala avtomatik yazılmır).",
        )
    return pgettext("appeals.notification", "Elektron jurnalda imtahan balı avtomatik yeniləndi.")


def notify_teachers_appeal_resolved(appeal, *, delta_points):
    """Apellyasiya qərarı balı DƏYİŞDİRƏNDƏ fənn müəlliminə bildiriş (dəyişməyibsə susur)."""
    try:
        if not delta_points:
            return
        from apps.notifications.public import create_notification_for_users

        exam = appeal.exam
        recipients = teacher_recipients(exam, [appeal.student_id])
        if not recipients:
            return
        student = appeal.student
        create_notification_for_users(
            recipients=recipients,
            title=pgettext("appeals.notification", "Apellyasiya nəticəsində bal dəyişdi"),
            message=pgettext(
                "appeals.notification",
                '{student} — "{exam}": apellyasiya qəbul olundu, bal {delta} dəyişdi. {hint}',
            ).format(
                student=student.get_full_name() or student.username,
                exam=exam.title,
                delta=_signed_points(delta_points),
                hint=_journal_hint(exam),
            ),
            link="",
            notification_type="grade",
            metadata={"appeal_id": appeal.id, "attempt_id": appeal.attempt_id, "exam_id": appeal.exam_id},
            organization=appeal.organization,
        )
    except Exception:
        logger.warning("Appeal teacher notification failed.", exc_info=True)


def notify_key_correction(correction, *, credited_attempts, question_no, revoked=False):
    """Açar düzəlişi (və ya geri alınması) — balı dəyişən tələbələrə + müəllimlərə bildiriş."""
    try:
        from apps.notifications.public import create_notification, create_notification_for_users

        exam = correction.exam
        results_link = reverse("accounts:profile") + "?section=my-results"
        for attempt in credited_attempts:
            if revoked:
                title = pgettext("appeals.notification", "Cavab açarı düzəlişi geri alındı")
                message = pgettext(
                    "appeals.notification",
                    '"{exam}" imtahanının {no}-ci sualı üzrə açar düzəlişi geri alındı — əlavə bal çıxarıldı.',
                ).format(exam=exam.title, no=question_no)
            else:
                title = pgettext("appeals.notification", "Cavab açarı düzəldildi")
                message = pgettext(
                    "appeals.notification",
                    '"{exam}" imtahanının {no}-ci sualının cavab açarı düzəldildi — balınız artırıldı.',
                ).format(exam=exam.title, no=question_no)
            create_notification(
                recipient=attempt.user,
                title=title,
                message=message,
                link=results_link,
                notification_type="grade",
                metadata={"key_correction_id": correction.id, "attempt_id": attempt.id, "exam_id": exam.id},
                organization=correction.organization,
            )
        recipients = teacher_recipients(exam, [attempt.user_id for attempt in credited_attempts])
        if recipients:
            create_notification_for_users(
                recipients=recipients,
                title=pgettext("appeals.notification", "Cavab açarı düzəlişi"),
                message=pgettext(
                    "appeals.notification",
                    '"{exam}" imtahanının {no}-ci sualı üzrə açar {action}: {count} tələbənin balı dəyişdi. {hint}',
                ).format(
                    exam=exam.title,
                    no=question_no,
                    action=(
                        pgettext("appeals.notification", "düzəlişi geri alındı")
                        if revoked
                        else pgettext("appeals.notification", "düzəldildi")
                    ),
                    count=len(credited_attempts),
                    hint=_journal_hint(exam),
                ),
                link="",
                notification_type="grade",
                metadata={"key_correction_id": correction.id, "exam_id": exam.id},
                organization=correction.organization,
            )
    except Exception:
        logger.warning("Answer-key correction notification failed.", exc_info=True)


__all__ = [
    "exam_center_recipients",
    "notify_key_correction",
    "notify_teachers_appeal_resolved",
    "teacher_recipients",
]
