"""«Qrupum» paneli — akademik qrupun siyahısı + cari dövrün fənn üzrə davamiyyət xülasəsi (OXU-YALNIZ).

Rol auditi 2026-10-13 B10: baş tələbə (``lead_student``) «qrup səviyyəli statistika» vədi ilə
``member.view`` daşıyırdı, amma heç bir səth onu oxumurdu. Bu modul həmin səthin DATASIDIR.

MÜQAVİLƏ:

* Qrupu çağıran VERİR — qapı accounts-dadır (``views/_helpers/rbac_my_group.my_group_unit``:
  ``member.view`` əhatəsi akademik qrup olmalıdır). Burada qrup seçimi/əhatə genişlənməsi YOXDUR:
  yalnız verilən qrupun ÖZ tələbələri (alt-ağac yox, başqa qrup yox).
* Minimal açıqlama: ad + tələbə nömrəsi + qayıb saatı/faizi. Əlaqə (e-poçt, telefon), demoqrafiya,
  bal, imtahan buraxılışı, idmançı istisnası GÖSTƏRİLMİR — status sözü əvəzinə yalnız faizin həddə
  nisbəti (``level``) verilir ki, istisna kimi şəxsi qərar qrup yoldaşına açılmasın.
* Yalnız QEYDİYYATLI (``enrolled``) aktiv qeydlər — akademik məzuniyyət/xaric statusu açılmır.
* Sorğu sayı tələbə/fənn sayından ASILI DEYİL: dövr (1) + qeydlər (1) + yazılışlar (1) + məxrəc
  fallback-i (yalnız ``lesson_hours`` boş açılış varsa, 1).
* Heç nə YAZMIR.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from apps.registrar import absence_limit, dashboard_data, exam_eligibility
from apps.registrar.models import AcademicStatus, Enrollment, StudentAcademicRecord

#: Hüceyrə səviyyələri (CSS sinfi ``mg-cell--<level>``) — həddin payı ilə.
LEVEL_NONE = "none"
LEVEL_OK = "ok"
LEVEL_NEAR = "near"
LEVEL_OVER = "over"


def _percent(part: Decimal, whole: Decimal):
    if whole <= 0:
        return None
    return int((part * Decimal(100) / whole).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _level(absence: Decimal, hours: Decimal, limit_percent: int) -> str:
    if hours <= 0 or absence <= 0:
        return LEVEL_NONE
    allowed = hours * Decimal(limit_percent) / Decimal(100)
    if absence > allowed:
        return LEVEL_OVER
    if absence >= allowed * absence_limit.WARN_RATIO:
        return LEVEL_NEAR
    return LEVEL_OK


def _student_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def group_overview(group, *, period=None) -> dict:
    """Qrupun siyahısı + cari dövrün davamiyyət matrisi.

    Qaytarır::

        {"group": OrgUnit, "period": AcademicPeriod | None,
         "subjects": [{"id", "name"}],
         "students": [{"name", "student_number", "absence_hours", "lesson_hours", "percent", "level",
                       "cells": [{"absence_hours", "lesson_hours", "percent", "level"} | None, ...]}],
         "has_attendance": bool}
    """
    result = {"group": group, "period": None, "subjects": [], "students": [], "has_attendance": False}
    if group is None:
        return result
    organization_id = group.organization_id
    if period is None:
        period = dashboard_data.current_period(group.organization)
    result["period"] = period

    records = list(
        StudentAcademicRecord.objects.filter(
            organization_id=organization_id, group=group, is_active=True, status=AcademicStatus.ENROLLED
        )
        .select_related("student", "student__profile", "program")
        .order_by("student__last_name", "student__first_name", "student__username", "pk")
    )
    # Eyni tələbənin iki proqram qeydi bu qrupa düşərsə bir sətir (İLK pk — ``absence_limit`` qaydası).
    by_student: dict = {}
    for record in sorted(records, key=lambda r: r.pk):
        by_student.setdefault(record.student_id, record)
    ordered = [record for record in records if by_student.get(record.student_id) is record]

    totals: dict = {}  # (student_id, subject_id) → [absence, hours]
    subjects: dict = {}  # subject_id → {"id", "name", "students": set(student_id)}
    if period is not None and ordered:
        rows = list(
            Enrollment.objects.filter(
                organization_id=organization_id, student_id__in=list(by_student), offering__period=period
            )
            .exclude(status=Enrollment.Status.DROPPED)
            .values(
                "student_id",
                "offering_id",
                "absence_hours",
                "offering__lesson_hours",
                "offering__subject_id",
                "offering__subject__name",
            )
        )
        lesson_hours_by_offering = _lesson_hours(rows)
        for row in rows:
            key = (row["student_id"], row["offering__subject_id"])
            bucket = totals.setdefault(key, [Decimal(0), Decimal(0)])
            bucket[0] += Decimal(row["absence_hours"] or 0)
            bucket[1] += lesson_hours_by_offering.get(row["offering_id"], Decimal(0))
            subject = subjects.setdefault(
                row["offering__subject_id"],
                {"id": row["offering__subject_id"], "name": row["offering__subject__name"] or "—", "students": set()},
            )
            subject["students"].add(row["student_id"])

    # Ortaq fənlər əvvəl (çox tələbə), sonra ad — seçmə fənn sütunu sona düşür.
    subject_list = sorted(subjects.values(), key=lambda s: (-len(s["students"]), (s["name"] or "").lower()))
    result["subjects"] = [{"id": s["id"], "name": s["name"]} for s in subject_list]
    result["has_attendance"] = bool(subject_list)

    for record in ordered:
        student = record.student
        limit_percent = absence_limit.limit_percent_for_record(record)
        cells = []
        absence_total = Decimal(0)
        hours_total = Decimal(0)
        for subject in subject_list:
            bucket = totals.get((record.student_id, subject["id"]))
            if bucket is None:
                cells.append(None)
                continue
            absence, hours = bucket
            absence_total += absence
            hours_total += hours
            cells.append(
                {
                    "absence_hours": absence,
                    "lesson_hours": hours,
                    "percent": _percent(absence, hours),
                    "level": _level(absence, hours, limit_percent),
                }
            )
        profile = getattr(student, "profile", None)
        result["students"].append(
            {
                "name": _student_name(student),
                "student_number": (getattr(profile, "institutional_identifier", "") or "") if profile else "",
                "absence_hours": absence_total,
                "lesson_hours": hours_total,
                "percent": _percent(absence_total, hours_total),
                "level": _level(absence_total, hours_total, limit_percent),
                "cells": cells,
            }
        )
    return result


def _lesson_hours(rows) -> dict:
    """offering_id → məxrəc (``exam_eligibility.lesson_hours_for`` qaydası, TƏK fallback sorğusu)."""
    planned = {row["offering_id"]: row["offering__lesson_hours"] or 0 for row in rows}
    missing = [oid for oid, hours in planned.items() if not hours > 0]
    fallback = exam_eligibility.lesson_hours_map(missing) if missing else {}
    return {oid: Decimal(hours) if hours > 0 else Decimal(fallback.get(oid) or 0) for oid, hours in planned.items()}


__all__ = ["LEVEL_NEAR", "LEVEL_NONE", "LEVEL_OK", "LEVEL_OVER", "group_overview"]
