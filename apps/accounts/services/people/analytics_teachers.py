"""«Müəllimlər» kataloqunun analitikası — bölgülər + dərs yükü göstəriciləri.

Sorğu büdcəsi (sətir sayından ASILI DEYİL):

1. scope həlli (icazə daşıyan üzvlüklər)       — 2
2. başlıq aqreqatı (say/status/cins/yaş)       — 1
3. struktur bölgüsü (scope_unit)               — 1
4. rol bölgüsü                                 — 1
5. vəzifə/dərəcə (`Membership.title`) bölgüsü  — 1
6. struktur adlarının toplu həlli              — 2
7. dərs yükü aqreqatı (açılışlar)              — 1
8. dərs yükü aqreqatı (qeydiyyatlar)           — 1

Ölçülmüş: **10 sorğu** (kataloq cədvəlinin 5 sorğusu POZULMUR). Demoqrafiya
icazəsi yoxdursa 2-ci sorğu daha da kiçilir; heç bir rəqəm sətir sayına bağlı
deyil.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Count
from django.utils.translation import pgettext_lazy

from .analytics import (
    counter_from,
    empty_analytics,
    headline,
    picked_rows,
    structure_counters,
    to_breakdown,
)
from .teachers import MEMBERSHIP_PICK_ORDER, filtered_teachers_qs, scoped_teacher_memberships

_CTX = "accounts.people.analytics"

_T_FACULTY = pgettext_lazy(_CTX, "Fakültə üzrə bölgü")
_T_KAFEDRA = pgettext_lazy(_CTX, "Kafedra üzrə bölgü")
_T_ROLE = pgettext_lazy(_CTX, "Rol üzrə bölgü")
_T_TITLE = pgettext_lazy(_CTX, "Akademik dərəcə / vəzifə")

_W_OFFERINGS = pgettext_lazy(_CTX, "Dərs açılışı (semestr-fənn)")
_W_SUBJECTS = pgettext_lazy(_CTX, "Fərqli fənn")
_W_GROUPS = pgettext_lazy(_CTX, "Dərs deyilən qrup")
_W_WITH_LOAD = pgettext_lazy(_CTX, "Dərs yükü olan müəllim")
_W_WITHOUT_LOAD = pgettext_lazy(_CTX, "Dərs yükü olmayan müəllim")
_W_AVG = pgettext_lazy(_CTX, "Müəllim başına orta açılış")
_W_SEATS = pgettext_lazy(_CTX, "Tələbə-yer (qeydiyyat)")


def _role_label(row) -> str:
    return (row.get("role__display_name") or row.get("role__name") or "").strip()


def _workload(*, organization, user_qs, filters, total_teachers: int) -> list:
    """Dərs yükü göstəriciləri — YALNIZ aqreqat (ad-soyad çıxmır).

    Filtrin tədris ili / semestr / fənn hissəsi açılışlara da tətbiq olunur ki,
    «2025/2026 Payız» süzgəci ilə göstərilən yük həmin semestrin yükü olsun.
    """
    from apps.registrar.models import CourseOffering, Enrollment

    offerings = CourseOffering.objects.filter(
        organization=organization,
        is_active=True,
        instructor__in=user_qs.values("pk"),
    )
    if filters.subject:
        offerings = offerings.filter(subject_id=filters.subject)
    if filters.year:
        offerings = offerings.filter(period__academic_year=filters.year)
    if filters.season:
        offerings = offerings.filter(period__name=filters.season)

    row = offerings.aggregate(
        offerings=Count("pk"),
        subjects=Count("subject_id", distinct=True),
        groups=Count("group_id", distinct=True),
        instructors=Count("instructor_id", distinct=True),
    )
    seats = Enrollment.objects.filter(organization=organization, offering__in=offerings).count()

    with_load = row.get("instructors") or 0
    offering_count = row.get("offerings") or 0
    average = round(offering_count / with_load, 1) if with_load else 0.0

    return [
        {"key": "offerings", "label": str(_W_OFFERINGS), "value": offering_count},
        {"key": "subjects", "label": str(_W_SUBJECTS), "value": row.get("subjects") or 0},
        {"key": "groups", "label": str(_W_GROUPS), "value": row.get("groups") or 0},
        {"key": "with_load", "label": str(_W_WITH_LOAD), "value": with_load},
        {"key": "without_load", "label": str(_W_WITHOUT_LOAD), "value": max(total_teachers - with_load, 0)},
        {"key": "avg_offerings", "label": str(_W_AVG), "value": average},
        {"key": "seats", "label": str(_W_SEATS), "value": seats},
    ]


def build_teacher_analytics(*, actor, filters, request=None, today: date | None = None) -> dict:
    """Müəllim kataloqunun cari filtr dəsti üzrə analitikası (fail-closed)."""
    if not actor.can_view_teachers or actor.organization is None:
        return empty_analytics("teachers", filters)

    memberships = scoped_teacher_memberships(actor, request=request, filters=filters)
    if memberships is None:
        return empty_analytics("teachers", filters)

    organization = actor.organization
    user_qs = filtered_teachers_qs(actor=actor, filters=filters, request=request)
    head = headline(user_qs, demographics=actor.can_view_demographics, today=today)
    total = head["total"]

    def group_by(*fields):
        return list(
            picked_rows(
                memberships,
                user_qs=user_qs,
                user_field="user",
                pick_order=MEMBERSHIP_PICK_ORDER,
                group_fields=fields,
            )
        )

    unit_rows = group_by("scope_unit_id")
    faculty, kafedra, _unit = structure_counters(unit_rows, organization=organization, id_key="scope_unit_id")
    role_counter = counter_from(group_by("role__name", "role__display_name"), _role_label)
    title_counter = counter_from(group_by("title"), lambda row: (row.get("title") or "").strip())

    breakdowns = [
        to_breakdown("faculty", _T_FACULTY, faculty, total=total),
        to_breakdown("kafedra", _T_KAFEDRA, kafedra, total=total),
        to_breakdown("role", _T_ROLE, role_counter, total=total, chart="doughnut"),
        to_breakdown("title", _T_TITLE, title_counter, total=total),
    ]

    return {
        "has_access": True,
        "kind": "teachers",
        "total": total,
        "can_view_demographics": actor.can_view_demographics,
        "status": head["status"],
        "gender": head["gender"],
        "age": head["age"],
        "breakdowns": breakdowns,
        "workload": _workload(
            organization=organization,
            user_qs=user_qs,
            filters=filters,
            total_teachers=total,
        ),
        "filters": filters.as_dict(),
    }


__all__ = ["build_teacher_analytics"]
