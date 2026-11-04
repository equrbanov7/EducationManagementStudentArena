"""«Alt qrup tələbələri» — statistika paneli (sahib 2026-11-05: «statistika hissəsində göstər ən çox hansı fəndən
olub və s.»).

Hamısı cari süzgəclərə tabedir (:func:`subgroup_students_read.filtered_queryset` ilə EYNİ sətirlər) və sorğu sayı
sabitdir: ümumi saylar bir aqreqatda, hər «ən çox» siyahısı bir ``GROUP BY``-da, fakültələr bir aqreqatda
(fakültə — tələbənin ÖZ qrupunun fakültəsi, ``OrgUnit.path`` prefiksi ilə), həftəlik trend bir ``GROUP BY``-da.
Aktor qapısı çağıranındır (bax :mod:`apps.registrar.subgroup_students_read`).
"""

from __future__ import annotations

import datetime as dt

from django.apps import apps as django_apps
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import OrgUnitType

from . import subgroup_students_read as read
from .models import CourseFormat, Enrollment

TOP_N = 8
TREND_WEEKS = 12


def _plain(queryset):
    """Sıralamasız (``GROUP BY``-a sıralama sahələri qarışmasın)."""
    return queryset.order_by()


def _top(queryset, fields, label) -> list:
    rows = _plain(queryset).values(*fields).annotate(total=Count("pk")).order_by("-total", *fields)[:TOP_N]
    items = [{"label": label(row), "count": row["total"]} for row in rows]
    peak = max((item["count"] for item in items), default=0)
    for item in items:
        # Tam ədəd: şablonda `style="--pct:NN%"` (lokal onluq vergülü CSS-i pozmasın).
        item["pct"] = round(item["count"] * 100 / peak) if peak else 0
    return items


def _teacher_label(row) -> str:
    full = " ".join(
        part for part in (row["offering__instructor__last_name"], row["offering__instructor__first_name"]) if part
    )
    return full.strip() or row["offering__instructor__username"] or pgettext(read.CTX, "Müəllim təyin olunmayıb")


def _target_label(row) -> str:
    if row["offering__group__name"]:
        return row["offering__group__name"]
    if row["offering__course_format"] == CourseFormat.INTENSIVE:
        return pgettext(read.CTX, "İntensiv kurs")
    return "—"


def totals(queryset) -> dict:
    """Ümumi saylar — BİR aqreqat. Açar adları annotasiya adları ilə (``waived`` / ``credits``) toqquşmamalıdır."""
    present = Q(has_file=True) | Q(has_order=True)
    waived = Q(waived=True, has_file=False, has_order=False)
    data = _plain(queryset).aggregate(
        n_total=Count("pk"),
        n_students=Count("student_id", distinct=True),
        n_active=Count("pk", filter=Q(status=Enrollment.Status.ENROLLED)),
        n_with_document=Count("pk", filter=present),
        n_waived=Count("pk", filter=waived),
        n_released=Count("pk", filter=Q(merged=True)),
        n_intensive=Count("pk", filter=Q(offering__course_format=CourseFormat.INTENSIVE)),
        n_credits=Sum("credits"),
    )
    result = {key[2:]: int(value or 0) for key, value in data.items()}
    result["without_document"] = max(0, result["total"] - result["with_document"] - result["waived"])
    return result


def faculty_counts(organization, queryset) -> list:
    """Tələbənin öz qrupunun fakültəsi üzrə say (bir aqreqat sorğusu; sıfırlar atılır)."""
    model = django_apps.get_model("organizations", "OrgUnit")
    faculties = list(
        model.objects.filter(organization=organization, unit_type=OrgUnitType.FACULTY, is_active=True)
        .order_by("name")
        .values_list("pk", "path", "name")
    )
    if not faculties:
        return []
    aggregates = {
        f"f{index}": Count(
            "pk",
            filter=Q(source_group_id=pk) | Q(source_group__path__startswith=f"{path or pk}/"),
        )
        for index, (pk, path, _name) in enumerate(faculties)
    }
    data = _plain(queryset).aggregate(**aggregates)
    items = [
        {"value": str(pk), "label": name, "count": data[f"f{index}"]}
        for index, (pk, _path, name) in enumerate(faculties)
        if data[f"f{index}"]
    ]
    items.sort(key=lambda item: (-item["count"], item["label"]))
    peak = max((item["count"] for item in items), default=0)
    for item in items:
        # Tam ədəd: şablonda `style="--pct:NN%"` (lokal onluq vergülü CSS-i pozmasın).
        item["pct"] = round(item["count"] * 100 / peak) if peak else 0
    return items


def weekly_trend(queryset, *, weeks=TREND_WEEKS) -> list:
    """Son ``weeks`` həftə üzrə əlavə sayı (boş həftələr 0 ilə) — sadə zolaq siyahısı üçün."""
    today = timezone.localdate()
    first = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks - 1)
    start = timezone.make_aware(dt.datetime.combine(first, dt.time.min))
    rows = (
        _plain(queryset)
        .filter(added_on__gte=start)
        .annotate(week=TruncWeek("added_on"))
        .values("week")
        .annotate(total=Count("pk"))
    )
    counts: dict = {}
    for row in rows:
        week = row["week"]
        if isinstance(week, dt.datetime):
            week = (timezone.localtime(week) if timezone.is_aware(week) else week).date()
        counts[week] = counts.get(week, 0) + row["total"]
    items = []
    for offset in range(weeks):
        monday = first + dt.timedelta(weeks=offset)
        items.append({"week": monday, "count": counts.get(monday, 0)})
    peak = max((item["count"] for item in items), default=0)
    for item in items:
        # Tam ədəd: şablonda `style="--pct:NN%"` (lokal onluq vergülü CSS-i pozmasın).
        item["pct"] = round(item["count"] * 100 / peak) if peak else 0
    return items


def build(organization, filters, scope=None) -> dict:
    """Bütün statistika bloku (cari süzgəclərlə)."""
    queryset = read.filtered_queryset(organization, filters, scope)
    return {
        "totals": totals(queryset),
        "subjects": _top(
            queryset,
            ("offering__subject__name", "offering__subject__code"),
            lambda row: f"{row['offering__subject__name']} ({row['offering__subject__code']})",
        ),
        "home_groups": _top(queryset, ("source_group__name",), lambda row: row["source_group__name"] or "—"),
        "target_groups": _top(queryset, ("offering__group__name", "offering__course_format"), _target_label),
        "teachers": _top(
            queryset,
            (
                "offering__instructor__last_name",
                "offering__instructor__first_name",
                "offering__instructor__username",
            ),
            _teacher_label,
        ),
        "faculties": faculty_counts(organization, queryset),
        "weeks": weekly_trend(queryset),
    }


__all__ = ["TOP_N", "TREND_WEEKS", "build", "faculty_counts", "totals", "weekly_trend"]
