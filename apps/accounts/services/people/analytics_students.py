"""«Tələbələr» kataloqunun analitikası — kurs, ixtisas, qrup, akademik status.

Sorğu büdcəsi (sətir sayından ASILI DEYİL):

1. scope həlli (icazə daşıyan üzvlüklər)  — 2
2. başlıq aqreqatı (say/status/cins/yaş)  — 1
3. qrup bölgüsü (group_id + adı)          — 1
4. ixtisas bölgüsü                        — 1
5. qəbul ili bölgüsü (→ kurs)             — 1
6. akademik status bölgüsü                — 1
7. struktur adlarının toplu həlli         — 2

Ölçülmüş: **9 sorğu**, sətir sayından asılı deyil.

**Kurs necə hesablanır.** Ayrıca «kurs» sahəsi YOXDUR — o, qəbul ilindən çıxarılır
(bax MEMORY «Academic term model»: tədris ili sentyabrda başlayır). Kurs =
cari tədris ilinin başlanğıcı − qəbul ili + 1. Real datada bəzi qeydlərdə qəbul
ili köhnədir; 1–8 aralığından kənar dəyər «Digər / məzun mərhələsi» səbətinə
düşür ki, qrafik uydurma kurs nömrəsi göstərməsin.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from django.utils.translation import pgettext_lazy

from .analytics import (
    UNSET_LABEL,
    academic_year_start,
    counter_from,
    empty_analytics,
    headline,
    picked_rows,
    structure_counters,
    to_breakdown,
)
from .students import RECORD_PICK_ORDER, filtered_students_qs, scoped_student_records

_CTX = "accounts.people.analytics"

_T_FACULTY = pgettext_lazy(_CTX, "Fakültə üzrə bölgü")
_T_KAFEDRA = pgettext_lazy(_CTX, "Kafedra üzrə bölgü")
_T_GROUP = pgettext_lazy(_CTX, "Qrup üzrə bölgü")
_T_PROGRAM = pgettext_lazy(_CTX, "İxtisas üzrə bölgü")
_T_COURSE = pgettext_lazy(_CTX, "Kurs üzrə bölgü")
_T_YEAR = pgettext_lazy(_CTX, "Qəbul ili üzrə bölgü")
_T_ACADEMIC = pgettext_lazy(_CTX, "Akademik status üzrə bölgü")

_COURSE_LABEL = pgettext_lazy(_CTX, "%(course)s. kurs")
_COURSE_OTHER = pgettext_lazy(_CTX, "Kursdan kənar / məzun mərhələsi")

MAX_COURSE = 8


def _program_label(row) -> str:
    code = (row.get("program__code") or "").strip()
    name = (row.get("program__name") or "").strip()
    if code and name:
        return f"{code} — {name}"
    return name or code


def _course_counter(year_rows, *, today: date | None = None) -> Counter:
    """Qəbul ili sətirlərindən kurs səbətləri (əlavə sorğu YOXDUR)."""
    start = academic_year_start(today)
    counter: Counter = Counter()
    for row in year_rows:
        admission = row.get("admission_year")
        value = row.get("bucket_total") or 0
        course = (start - admission + 1) if admission else None
        if course is None or course < 1 or course > MAX_COURSE:
            counter[str(_COURSE_OTHER)] += value
        else:
            counter[str(_COURSE_LABEL % {"course": course})] += value
    return counter


def _academic_status_labels() -> dict:
    from apps.registrar.models import AcademicStatus

    return {value: str(label) for value, label in AcademicStatus.choices}


def build_student_analytics(*, actor, filters, request=None, today: date | None = None) -> dict:
    """Tələbə kataloqunun cari filtr dəsti üzrə analitikası (fail-closed)."""
    if not actor.can_view_students or actor.organization is None:
        return empty_analytics("students", filters)

    records = scoped_student_records(actor, request=request, filters=filters)
    if records is None:
        return empty_analytics("students", filters)

    organization = actor.organization
    user_qs = filtered_students_qs(actor=actor, filters=filters, request=request)
    head = headline(user_qs, demographics=actor.can_view_demographics, today=today)
    total = head["total"]

    def group_by(*fields):
        return list(
            picked_rows(
                records,
                user_qs=user_qs,
                user_field="student",
                pick_order=RECORD_PICK_ORDER,
                group_fields=fields,
            )
        )

    group_rows = group_by("group_id", "group__name")
    faculty, kafedra, _unit = structure_counters(group_rows, organization=organization, id_key="group_id")
    group_counter = counter_from(group_rows, lambda row: (row.get("group__name") or "").strip())
    program_counter = counter_from(group_by("program__code", "program__name"), _program_label)

    year_rows = group_by("admission_year")
    year_counter = counter_from(year_rows, lambda row: str(row.get("admission_year") or "") or UNSET_LABEL)
    course_counter = _course_counter(year_rows, today=today)

    status_labels = _academic_status_labels()
    academic_counter = counter_from(
        group_by("status"),
        lambda row: status_labels.get(row.get("status"), row.get("status") or ""),
    )

    breakdowns = [
        to_breakdown("faculty", _T_FACULTY, faculty, total=total),
        to_breakdown("kafedra", _T_KAFEDRA, kafedra, total=total),
        to_breakdown("program", _T_PROGRAM, program_counter, total=total),
        to_breakdown("course", _T_COURSE, course_counter, total=total, chart="doughnut", order="label"),
        to_breakdown("group", _T_GROUP, group_counter, total=total),
        to_breakdown("admission_year", _T_YEAR, year_counter, total=total, order="label"),
        to_breakdown("academic_status", _T_ACADEMIC, academic_counter, total=total, chart="doughnut"),
    ]

    return {
        "has_access": True,
        "kind": "students",
        "total": total,
        "can_view_demographics": actor.can_view_demographics,
        "status": head["status"],
        "gender": head["gender"],
        "age": head["age"],
        "breakdowns": breakdowns,
        "workload": [],
        "filters": filters.as_dict(),
    }


__all__ = ["build_student_analytics"]
