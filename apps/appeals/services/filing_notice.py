"""Teacher Exam Center invitation and subject-chair observers for the same filed event."""

from django.utils.translation import pgettext

from core.person_names import user_display_name_with_patronymic

from .student_identity import student_group_map
from .subject_scope import notification_readers


def actual_teachers(appeal):
    """Live teachers of exam-linked student offerings, never an author fallback."""
    from django.apps import apps as django_apps
    from django.contrib.auth import get_user_model

    from apps.registrar.public import eligible_instructor_user_ids

    from .subject_scope import selected_offerings

    organization = appeal.organization
    Appeal = django_apps.get_model("appeals", "Appeal")
    Offering = django_apps.get_model("registrar", "CourseOffering")
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    Slot = django_apps.get_model("registrar", "ScheduleSlot")
    Share = django_apps.get_model("registrar", "JournalShare")
    _rows, selected = selected_offerings(Appeal.objects.filter(pk=appeal.pk), organization)
    offering_ids = selected.get(appeal.pk, [])
    ids = set(
        Offering.objects.filter(organization=organization, pk__in=offering_ids).values_list("instructor_id", flat=True)
    )
    slots = Slot.objects.filter(organization=organization, offering_id__in=offering_ids)
    if hasattr(Slot, "deleted_at"):
        slots = slots.filter(deleted_at__isnull=True)
    ids.update(slots.values_list("instructor_id", flat=True))
    enrollment_ids = set(
        Enrollment.objects.filter(
            organization=organization,
            student_id=appeal.student_id,
            offering__organization=organization,
            offering_id__in=offering_ids,
        )
        .exclude(status="dropped")
        .values_list("pk", flat=True)
    )
    shares = Share.objects.filter(
        organization=organization,
        offering__organization=organization,
        offering_id__in=offering_ids,
        is_active=True,
    ).prefetch_related("enrollments")
    for share in shares:
        picked = {row.pk for row in share.enrollments.all()}
        if not picked or picked & enrollment_ids:
            ids.add(share.teacher_id)
    if appeal.exam.journal_teacher_id:
        ids.add(appeal.exam.journal_teacher_id)
    allowed = eligible_instructor_user_ids(organization=organization)
    ids = (ids & allowed) - {appeal.student_id}
    return list(get_user_model().objects.filter(pk__in=ids, is_active=True).order_by("pk"))


def notify(appeal, *, teachers, exclude_ids=(), item_count, link):
    from apps.appeals.models import Appeal
    from apps.notifications.public import create_notification_for_users

    excluded = {appeal.student_id, *exclude_ids}
    teachers = [user for user in teachers if user.pk not in excluded]
    names = ", ".join(user_display_name_with_patronymic(user) for user in teachers)
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
