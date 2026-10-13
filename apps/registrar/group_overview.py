"""«Starosta» (`my-group`) paneli — akademik qrupun siyahısı + BAXANIN ÖZ davamiyyəti (OXU-YALNIZ).

Rol auditi 2026-10-13 B10: baş tələbə (``lead_student``) «qrup səviyyəli» ``member.view`` daşıyırdı, amma
heç bir səth onu oxumurdu. Bu modul həmin səthin DATASIDIR.

MÜQAVİLƏ:

* Qrupu çağıran VERİR — qapı accounts-dadır (``views/_helpers/rbac_my_group.my_group_unit``:
  ``member.view`` əhatəsi akademik qrup olmalıdır). Burada qrup seçimi/əhatə genişlənməsi YOXDUR:
  yalnız verilən qrupun ÖZ tələbələri (alt-ağac yox, başqa qrup yox).
* Sahib 2026-10-13: «ancaq şəxsi görünsün» — qrup yoldaşları üçün YALNIZ ad + tələbə nömrəsi. Davamiyyət
  (qayıb saatı/faizi) şəxsi məlumatdır və YALNIZ baxanın öz sətri üçün hesablanır (``viewer_id``);
  başqasının qayıbı, balı, əlaqəsi, demoqrafiyası, imtahan buraxılışı, idmançı istisnası GÖSTƏRİLMİR.
* Yalnız QEYDİYYATLI (``enrolled``) aktiv qeydlər — akademik məzuniyyət/xaric statusu açılmır.
* Sorğu sayı tələbə/fənn sayından ASILI DEYİL: dövr (1) + qeydlər (1) + baxanın yazılışları (1) + məxrəc
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


def group_overview(group, *, viewer_id=None, period=None) -> dict:
    """Qrupun siyahısı + baxanın (``viewer_id``) cari dövr üzrə fənn davamiyyəti.

    Qaytarır::

        {"group": OrgUnit, "period": AcademicPeriod | None,
         "students": [{"name", "student_number", "is_me"}],
         "me": {"subjects": [{"name", "absence_hours", "lesson_hours", "percent", "level"}],
                "absence_hours", "lesson_hours", "percent", "level"} | None,
         "has_attendance": bool}

    ``me`` yalnız baxan HƏMİN qrupda qeydiyyatlı tələbədirsə doludur.
    """
    result = {"group": group, "period": None, "students": [], "me": None, "has_attendance": False}
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

    for record in ordered:
        profile = getattr(record.student, "profile", None)
        result["students"].append(
            {
                "name": _student_name(record.student),
                "student_number": (getattr(profile, "institutional_identifier", "") or "") if profile else "",
                "is_me": viewer_id is not None and record.student_id == viewer_id,
            }
        )

    own_record = by_student.get(viewer_id) if viewer_id is not None else None
    if own_record is None:
        return result
    result["me"] = _own_attendance(own_record, period, organization_id)
    result["has_attendance"] = bool(result["me"]["subjects"])
    return result


def _own_attendance(record, period, organization_id) -> dict:
    """Baxanın öz qeydi üçün fənn üzrə qayıb/məxrəc (dövr yoxdursa boş)."""
    totals: dict = {}  # subject_id → {"name", "absence", "hours"}
    if period is not None:
        rows = list(
            Enrollment.objects.filter(
                organization_id=organization_id, student_id=record.student_id, offering__period=period
            )
            .exclude(status=Enrollment.Status.DROPPED)
            .values(
                "offering_id",
                "absence_hours",
                "offering__lesson_hours",
                "offering__subject_id",
                "offering__subject__name",
            )
        )
        lesson_hours_by_offering = _lesson_hours(rows)
        for row in rows:
            bucket = totals.setdefault(
                row["offering__subject_id"],
                {"name": row["offering__subject__name"] or "—", "absence": Decimal(0), "hours": Decimal(0)},
            )
            bucket["absence"] += Decimal(row["absence_hours"] or 0)
            bucket["hours"] += lesson_hours_by_offering.get(row["offering_id"], Decimal(0))

    limit_percent = absence_limit.limit_percent_for_record(record)
    subjects = []
    absence_total = Decimal(0)
    hours_total = Decimal(0)
    for bucket in sorted(totals.values(), key=lambda b: (b["name"] or "").lower()):
        absence_total += bucket["absence"]
        hours_total += bucket["hours"]
        subjects.append(
            {
                "name": bucket["name"],
                "absence_hours": bucket["absence"],
                "lesson_hours": bucket["hours"],
                "percent": _percent(bucket["absence"], bucket["hours"]),
                "level": _level(bucket["absence"], bucket["hours"], limit_percent),
            }
        )
    return {
        "subjects": subjects,
        "absence_hours": absence_total,
        "lesson_hours": hours_total,
        "percent": _percent(absence_total, hours_total),
        "level": _level(absence_total, hours_total, limit_percent),
    }


def _lesson_hours(rows) -> dict:
    """offering_id → məxrəc (``exam_eligibility.lesson_hours_for`` qaydası, TƏK fallback sorğusu)."""
    planned = {row["offering_id"]: row["offering__lesson_hours"] or 0 for row in rows}
    missing = [oid for oid, hours in planned.items() if not hours > 0]
    fallback = exam_eligibility.lesson_hours_map(missing) if missing else {}
    return {oid: Decimal(hours) if hours > 0 else Decimal(fallback.get(oid) or 0) for oid, hours in planned.items()}


__all__ = ["LEVEL_NEAR", "LEVEL_NONE", "LEVEL_OK", "LEVEL_OVER", "group_overview"]
