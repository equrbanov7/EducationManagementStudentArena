"""Teacher Exam Center invitation and subject-chair observers for the same filed event."""

from django.utils.translation import pgettext

from core.person_names import user_display_name_with_patronymic

from .student_identity import student_group_map
from .subject_scope import notification_readers


def actual_teachers(appeal):
    """Existing offering teacher resolver, plus the explicit exam journal teacher.

    Only live same-tenant grading teachers qualify. Exam-center authors are not
    mistaken for the subject teacher merely because they created the exam.
    """
    from apps.registrar.public import eligible_instructor_user_ids

    from .teachers import subject_teachers

    allowed = eligible_instructor_user_ids(organization=appeal.organization)
    candidates = list(subject_teachers(appeal))
    if appeal.exam.journal_teacher_id:
        candidates.insert(0, appeal.exam.journal_teacher)
    result = {}
    for user in candidates:
        if user.pk in allowed and user.pk != appeal.student_id:
            result.setdefault(user.pk, user)
    return list(result.values())


def notify(appeal, *, teachers, exclude_ids=(), item_count, link):
    from apps.appeals.models import Appeal
    from apps.notifications.public import create_notification_for_users

    excluded = {appeal.student_id, *exclude_ids}
    names = ", ".join(user_display_name_with_patronymic(user) for user in teachers)
    teachers = [user for user in teachers if user.pk not in excluded]
    teacher_ids = {user.pk for user in teachers}
    readers = [user for user in notification_readers(appeal) if user.pk not in excluded | teacher_ids]
    groups = student_group_map(Appeal.objects.filter(organization=appeal.organization, pk=appeal.pk))
    student = user_display_name_with_patronymic(appeal.student)
    subject = appeal.exam.subject.name if appeal.exam.subject_id else appeal.exam.title
    facts = pgettext(
        "appeals.notification",
        "Tələbə: {student} ({username}); qrup: {group}; fənn: {subject}; imtahan: {exam}; sual sayı: {count}.",
    ).format(
        student=student,
        username=appeal.student.username,
        group=groups.get(appeal.student_id) or "—",
        subject=subject,
        exam=appeal.exam.title,
        count=item_count,
    )
    common = {
        "link": link,
        "notification_type": "exam",
        "organization": appeal.organization,
        "metadata": {"appeal_id": appeal.pk, "attempt_id": appeal.attempt_id, "exam_id": appeal.exam_id},
    }
    if teachers:
        message = pgettext(
            "appeals.notification",
            "Müəllim: {teachers}. Apellyasiya ilə bağlı İmtahan Mərkəzinə yaxınlaşın. {details}",
        ).format(teachers=names, details=facts)
        create_notification_for_users(
            recipients=teachers,
            title=pgettext("appeals.notification", "Tələbəniz apellyasiya verdi"),
            message=message,
            **common,
        )
    if readers:
        message = facts
        if names:
            message = pgettext(
                "appeals.notification",
                "Fənni tədris edən müəllim: {teachers}. Müəllim apellyasiya ilə bağlı İmtahan Mərkəzinə dəvət olunur. {details}",
            ).format(teachers=names, details=facts)
        create_notification_for_users(
            recipients=readers,
            title=pgettext("appeals.notification", "Fənn üzrə yeni apellyasiya"),
            message=message,
            **common,
        )
