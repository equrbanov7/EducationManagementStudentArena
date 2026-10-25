"""Registrar ictimai səthi — «İntensiv kurs» (sahib 2026-10-25).

Dərs yükü modulu (``apps.workload.services.intensive``) intensiv kursun açılışını / qeydiyyatını YALNIZ bu adlarla
işlədir (bax :mod:`apps.registrar.intensive`):

* ``open_intensive_course(...)`` — açılış + qeydiyyatlar (bir tranzaksiya), :class:`IntensiveError` atır;
* ``check_intensive_students(...)`` — ön baxış: hər tələbə ``ok`` / ``conflict`` / ``blocked``;
* ``cancel_intensive_course(...)`` — dərssiz kursu ləğv (köçürülmüş qeydiyyatlar geri qayıdır);
* ``search_intensive_students(...)`` — ad / qrup / istifadəçi adı ilə axtarış (``EMSSearchableSelect``).
"""

from __future__ import annotations

from core.search_text import tolerant_q

from .intensive import ARCHIVED_ACCESS, IntensiveError
from .intensive import cancel_course as cancel_intensive_course
from .intensive import check_students as check_intensive_students
from .intensive import open_course as open_intensive_course
from .intensive import public_check
from .models import AcademicStatus, CourseFormat, StudentAcademicRecord

intensive_public_check = public_check


def search_intensive_students(*, organization, q="", offset=0, limit=20) -> dict:
    """Oxuyan tələbələr — ``{"results": [{"id", "text", "hint"}], "has_more"}`` (bütün təşkilat)."""
    queryset = StudentAcademicRecord.objects.filter(
        organization=organization, is_active=True, status=AcademicStatus.ENROLLED, group__isnull=False
    ).exclude(student__profile__access_state=ARCHIVED_ACCESS)
    search = tolerant_q(
        q,
        ("student__first_name", "student__last_name", "student__username"),
        compact_fields=("group__name", "student__profile__institutional_identifier"),
    )
    if search is not None:
        queryset = queryset.filter(search)
    window = list(
        queryset.select_related("student", "group").order_by(
            "student__last_name", "student__first_name", "student__username", "-created_at"
        )[offset : offset + limit + 1]
    )
    seen, results = set(), []
    for record in window[:limit]:
        if record.student_id in seen:
            continue
        seen.add(record.student_id)
        name = (record.student.get_full_name() or "").strip() or record.student.username
        results.append(
            {"id": str(record.student_id), "text": f"{name} · {record.group.name}", "hint": record.group.name}
        )
    return {"results": results, "has_more": len(window) > limit}


__all__ = [
    "CourseFormat",
    "IntensiveError",
    "cancel_intensive_course",
    "check_intensive_students",
    "intensive_public_check",
    "open_intensive_course",
    "search_intensive_students",
]
