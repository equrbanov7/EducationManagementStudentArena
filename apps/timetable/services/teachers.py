"""Əhatədəki müəllimlər və onların fənləri (əlçatanlıq ekranı üçün, YALNIZ OXU)."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Count

from apps.registrar.public import schedule_grid, schedule_manage

from . import access, availability


def _name(user) -> str:
    full = (user.get_full_name() or "").strip()
    return full or user.username


def teacher_rows(actor, organization, period, *, query="") -> list:
    """Müəllim siyahısı: ad, açılış sayı, əlçatanlıq xülasəsi (sorğu sayı sabitdir)."""
    ids = access.scoped_teacher_ids(actor, organization, period)
    users = get_user_model().objects.filter(pk__in=ids).order_by("first_name", "last_name", "username")
    words = [word for word in str(query or "").casefold().split() if word]
    offerings = schedule_manage.scoped_offerings(actor, organization, period=period)
    counts = dict(
        offerings.filter(instructor_id__in=ids)
        .values("instructor_id")
        .annotate(n=Count("id"))
        .values_list("instructor_id", "n")
    )
    Availability = django_apps.get_model("timetable", "TeacherAvailability")
    rows_by_teacher = {
        row.teacher_id: row for row in Availability.objects.filter(organization=organization, period=period)
    }
    periods = len(schedule_grid.lesson_periods(organization))
    out = []
    for user in users:
        name = _name(user)
        if words and not all(word in f"{name} {user.username}".casefold() for word in words):
            continue
        out.append(
            {
                "id": user.pk,
                "name": name,
                "username": user.username,
                "offerings": counts.get(user.pk, 0),
                "availability": availability.summary(rows_by_teacher.get(user.pk), periods),
            }
        )
    return out


def teacher_subjects(actor, organization, period, teacher) -> list:
    """Müəllimin bu semestr fənləri: açılışın müəllimi olduğu + tapşırıqda bölünənlər."""
    offerings = schedule_manage.scoped_offerings(actor, organization, period=period).select_related("subject", "group")
    subjects: dict = {}

    def add(subject, group_name, kind, hours=None):
        item = subjects.setdefault(
            str(subject.pk),
            {
                "subject_id": str(subject.pk),
                "code": subject.code or "",
                "name": subject.name or "",
                "groups": [],
                "kinds": {},
            },
        )
        if group_name and group_name not in item["groups"]:
            item["groups"].append(group_name)
        if kind:
            item["kinds"][kind] = max(int(hours or 0), item["kinds"].get(kind, 0))

    for offering in offerings.filter(instructor=teacher).order_by("subject__code", "group__name"):
        add(offering.subject, getattr(offering.group, "name", ""), "")
    try:
        Assignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:
        Assignment = None
    if Assignment is not None:
        rows = (
            Assignment.objects.filter(
                organization=organization, teacher=teacher, row__period=period, row__subject__isnull=False
            )
            .select_related("row__subject")
            .prefetch_related("row__groups")
            .order_by("row__subject__code", "activity")
        )
        scoped = set(offerings.values_list("group_id", flat=True))
        for item in rows:
            groups = [g.name for g in item.row.groups.all() if g.pk in scoped]
            if not groups:
                continue
            for name in groups:
                add(item.row.subject, name, item.activity, item.hours)
    return sorted(subjects.values(), key=lambda row: (row["code"], row["name"]))


__all__ = ["teacher_rows", "teacher_subjects"]
