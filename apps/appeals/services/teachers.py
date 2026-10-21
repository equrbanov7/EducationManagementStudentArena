"""Apellyasiya — «Fənni tədris edən» və «Qərarı verən müəllim» (sahib 2026-10-21).

Sahib: «Orada sistem özü də göstərsin ki o fənni tədris edən kimdir — kimlər buna baxa biləcək aktiv
müəllimlərdən: fənnin öz müəllimi, yəni qrupun (həmin tələbənin qrupunda bu fənni keçən). … həmin müəllimin də
səhifəsində görünsün bu».

**Fənni tədris edən** (:func:`subject_teachers`) — sistem özü hesablayır:

1. tələbənin imtahan fənni (``exam.subject``) üzrə qeydiyyatları (``registrar.Enrollment``, ləğv olunmamış);
2. imtahan anını (``attempt.finished_at`` / müraciət vaxtı) əhatə edən dövrün açılışı; yoxdursa ən son dövr;
3. həmin açılışın jurnal sahibi (``offering.instructor``) + cədvəldə slotu aparan müəllimlər
   (``ScheduleSlot.instructor`` — bölünmüş tədris: seminar/laboratoriya);
4. heç biri yoxdursa — imtahanın müəllifi.

YALNIZ aktiv (``is_active``) hesablar, tələbənin özü heç vaxt. Bunlar «Qərarı verən müəllim» seçicisinin ilk
variantlarıdır; tək müəllim varsa defolt seçilir. Qalan variantlar — təşkilatda bal yaza bilən aktiv üzvlər
(``registrar.public.eligible_instructor_user_ids``, açılış formasının eyni siyahısı).

**Müəllim görünüşü** (:func:`teaching_appeals_queryset`) — müəllim YALNIZ öz tədris etdiyi açılışların (jurnal
sahibi və ya slot müəllimi) tələbələrinin həmin fənn üzrə apellyasiyalarını görür (yalnız-oxu; qərar hüququ yoxdur).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Q

_DROPPED = "dropped"


def _person(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username()).strip()


def _enrollment_model():
    try:
        return django_apps.get_model("registrar", "Enrollment")
    except LookupError:  # registrar quraşdırılmayıb
        return None


def _appeal_moment(appeal):
    attempt = getattr(appeal, "attempt", None)
    moment = getattr(attempt, "finished_at", None) or getattr(appeal, "created_at", None)
    return moment.date() if moment else None


def _subject_offering_ids(appeal) -> list:
    """Tələbənin imtahan fənni üzrə açılışları — imtahan anının dövrü əvvəl, sonra ən son dövr."""
    exam = appeal.exam
    enrollment_model = _enrollment_model()
    if enrollment_model is None or not getattr(exam, "subject_id", None):
        return []
    rows = list(
        enrollment_model.objects.filter(
            student_id=appeal.student_id,
            offering__subject_id=exam.subject_id,
            offering__organization_id=exam.organization_id,
        )
        .exclude(status=_DROPPED)
        .values_list("offering_id", "offering__period__start_date", "offering__period__end_date")
    )
    if not rows:
        return []
    moment = _appeal_moment(appeal)
    covering = [pk for pk, start, end in rows if moment and start and end and start <= moment <= end]
    if covering:
        return covering
    latest = max((start for _pk, start, _end in rows if start), default=None)
    return [pk for pk, start, _end in rows if start == latest] or [rows[0][0]]


def _offering_teacher_ids(offering_ids) -> list:
    """Açılışların jurnal sahibi + cədvəl slotlarını aparan müəllimlər (sıra: sahib əvvəl)."""
    if not offering_ids:
        return []
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    ordered = []
    for instructor_id in offering_model.objects.filter(pk__in=offering_ids).values_list("instructor_id", flat=True):
        if instructor_id and instructor_id not in ordered:
            ordered.append(instructor_id)
    try:
        slot_model = django_apps.get_model("registrar", "ScheduleSlot")
        slot_rows = slot_model.objects.filter(offering_id__in=offering_ids, instructor_id__isnull=False)
        if hasattr(slot_model, "deleted_at"):
            slot_rows = slot_rows.filter(deleted_at__isnull=True)
        for instructor_id in slot_rows.values_list("instructor_id", flat=True).distinct():
            if instructor_id not in ordered:
                ordered.append(instructor_id)
    except LookupError:
        pass
    return ordered


def _active_users_in_order(user_ids, *, exclude_id=None):
    ids = [pk for pk in user_ids if pk and pk != exclude_id]
    if not ids:
        return []
    by_id = {user.pk: user for user in get_user_model().objects.filter(pk__in=ids, is_active=True)}
    return [by_id[pk] for pk in ids if pk in by_id]


def subject_teachers(appeal) -> list:
    """«Fənni tədris edən» AKTİV müəllimlər (modul sənədinə bax); boşdursa imtahanın müəllifi."""
    cached = getattr(appeal, "_subject_teachers_cache", None)
    if cached is not None:
        return cached
    teachers = _active_users_in_order(
        _offering_teacher_ids(_subject_offering_ids(appeal)), exclude_id=appeal.student_id
    )
    if not teachers:
        teachers = _active_users_in_order([getattr(appeal.exam, "author_id", None)], exclude_id=appeal.student_id)
    appeal._subject_teachers_cache = teachers
    return teachers


def subject_teacher_names(appeal) -> str:
    return ", ".join(_person(user) for user in subject_teachers(appeal))


def attach_subject_teachers(appeals) -> list:
    """Siyahı sətirləri üçün ``appeal.subject_teacher_names`` (səhifədə ≤ 20 sətir — sətir başına 3 dar sorğu)."""
    for appeal in appeals:
        appeal.subject_teacher_names = subject_teacher_names(appeal)
    return appeals


def organization_teacher_ids(organization) -> set:
    if organization is None:
        return set()
    try:
        from apps.registrar.public import eligible_instructor_user_ids
    except ImportError:  # pragma: no cover — registrar yoxdur
        return set()
    return {int(pk) for pk in eligible_instructor_user_ids(organization=organization)}


def decision_teacher_options(appeal) -> dict:
    """Seçici üçün: ``{"subject": [...], "others": [...], "default_id": int|None}`` (yalnız aktiv, tələbəsiz)."""
    subject = subject_teachers(appeal)
    subject_ids = {user.pk for user in subject}
    other_ids = organization_teacher_ids(appeal.organization) - subject_ids - {appeal.student_id}
    others = list(
        get_user_model()
        .objects.filter(pk__in=other_ids, is_active=True)
        .order_by("last_name", "first_name", "username")
    )
    return {
        "subject": [{"id": user.pk, "label": _person(user)} for user in subject],
        "others": [{"id": user.pk, "label": _person(user)} for user in others],
        "default_id": subject[0].pk if len(subject) == 1 else None,
    }


def resolve_decision_teacher(appeal, raw_value):
    """POST-dan gələn müəllim id-si → aktiv ``User`` (fənn müəllimi və ya təşkilatın müəllimi) və ya ``None``."""
    try:
        teacher_id = int(str(raw_value or "").strip())
    except (TypeError, ValueError):
        return None
    if teacher_id == appeal.student_id:
        return None
    allowed = {user.pk for user in subject_teachers(appeal)} | organization_teacher_ids(appeal.organization)
    if teacher_id not in allowed:
        return None
    return get_user_model().objects.filter(pk=teacher_id, is_active=True).first()


# ── Müəllim görünüşü ──────────────────────────────────────────────────────────


def taught_offering_ids(user, organization) -> list:
    """Bu müəllimin tədris etdiyi açılışlar (jurnal sahibi və ya cədvəl slotunun müəllimi)."""
    if organization is None or not getattr(user, "is_authenticated", False):
        return []
    try:
        offering_model = django_apps.get_model("registrar", "CourseOffering")
        slot_model = django_apps.get_model("registrar", "ScheduleSlot")
    except LookupError:
        return []
    slot_offerings = slot_model.objects.filter(instructor_id=user.pk, organization_id=organization.pk)
    if hasattr(slot_model, "deleted_at"):
        slot_offerings = slot_offerings.filter(deleted_at__isnull=True)
    return list(
        offering_model.objects.filter(organization_id=organization.pk)
        .filter(Q(instructor_id=user.pk) | Q(pk__in=slot_offerings.values("offering_id")))
        .values_list("pk", flat=True)
    )


def teaching_appeals_queryset(user, organization):
    """Müəllimin tədris etdiyi açılışların tələbələrinin həmin fənn üzrə apellyasiyaları (yalnız-oxu)."""
    from apps.appeals.models import Appeal

    offering_ids = taught_offering_ids(user, organization)
    enrollment_model = _enrollment_model()
    if not offering_ids or enrollment_model is None:
        return Appeal.objects.none()
    pairs = enrollment_model.objects.filter(offering_id__in=offering_ids).exclude(status=_DROPPED)
    subject_ids = set(pairs.values_list("offering__subject_id", flat=True))
    student_ids = set(pairs.values_list("student_id", flat=True))
    if not subject_ids or not student_ids:
        return Appeal.objects.none()
    candidates = Appeal.objects.filter(
        organization_id=organization.pk, exam__subject_id__in=subject_ids, student_id__in=student_ids
    )
    allowed_pairs = set(pairs.values_list("student_id", "offering__subject_id"))
    keep = [
        pk
        for pk, sid, subj in candidates.values_list("pk", "student_id", "exam__subject_id")
        if (sid, subj) in allowed_pairs
    ]
    return Appeal.objects.filter(pk__in=keep)


def teaches_appeal(user, appeal) -> bool:
    """Bu istifadəçi apellyasiyanın «fənni tədris edən» müəllimlərindəndirmi (yalnız-oxu baxış üçün)."""
    if not getattr(user, "is_authenticated", False) or user.pk == appeal.student_id:
        return False
    return any(teacher.pk == user.pk for teacher in subject_teachers(appeal))


__all__ = [
    "attach_subject_teachers",
    "decision_teacher_options",
    "organization_teacher_ids",
    "resolve_decision_teacher",
    "subject_teacher_names",
    "subject_teachers",
    "taught_offering_ids",
    "teaches_appeal",
    "teaching_appeals_queryset",
]
