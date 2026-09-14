"""Davamiyyət (qayıb) həddinin TƏK MƏNBƏDƏN həlli — tələbənin ÖZ proqramı.

Backend auditi 2026-09-13, F-06 (P2). Həddin özü həmişə
``Program.absence_limit_percent`` idi, amma HANSI proqramın götürüləcəyi iki
yolla həll olunurdu:

* kabinet / transkript / «Fənlərim» — tələbənin ÖZ ``StudentAcademicRecord``-u
  (``services.get_student_cabinet_data``, ``cabinet_policy``);
* imtahana START QAPISI (``exam_bridge.exam_eligibility``) və tələbə jurnal
  detalı (``public.build_student_journal_context``) —
  ``gradebook.absence_limit_percent_for(offering)``: açılışın QRUPUNDAKI
  İLK (pk) akademik qeydin proqramı.

Qonaq / alt-qrup tələbə başqa proqramdan gələndə (fərqli
``absence_limit_percent``) kabinet «buraxılır», imtahan qapısı isə «kəsilib»
deyirdi (və ya əksinə); sandbox reproda eyni tələbə üçün gate=25, cabinet=10.
Bu modul hər iki tərəfin çağırdığı ORTAQ resolver-dir: hədd YALNIZ tələbənin
öz qeydindən gəlir. Kabinetlə eyni seçim qaydası saxlanılır — (təşkilat,
tələbə) üzrə İLK (pk) qeyd (``public.py``-dakı ``.first()`` ilə birə-bir).

Dalğa 2 (2026-09-14, hesabat §27 / backend F-06 qalıqları): qalan dörd səth də
buraya bağlandı — ``finals.compute_final_result`` (tək və toplu yol),
``journal_extras.get_final_breakdown`` («Yekun» tabı) və müəllim qridi
(``gradebook.get_offering_journal``) sətir-sətir TƏLƏBƏNİN ÖZ həddi ilə qərar
verir (:func:`row_limits`, tək toplu sorğu). Açılış-səviyyəli
:func:`limit_percent_for_offering` (qrupun ilk qeydi) YALNIZ başlıq sütunu
(«limit N q/b») üçün qalır — buraxılış qərarı artıq ondan çıxmır.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from apps.registrar import exam_eligibility
from apps.registrar.exam_eligibility import DEFAULT_LIMIT_PERCENT
from apps.registrar.models import StudentAcademicRecord


def limit_percent_for_record(record) -> int:
    """Akademik qeydin proqram həddi; qeyd/proqram yoxdursa defolt (25)."""
    program = getattr(record, "program", None) if record is not None else None
    value = getattr(program, "absence_limit_percent", None)
    return int(value) if value is not None else DEFAULT_LIMIT_PERCENT


def limit_percent_for_student(*, organization_id, student_id) -> int:
    """Tələbənin ÖZ proqramının həddi — 1 sorğu; kabinetlə eyni qeyd seçimi."""
    if organization_id is None or student_id is None:
        return DEFAULT_LIMIT_PERCENT
    record = (
        StudentAcademicRecord.objects.filter(organization_id=organization_id, student_id=student_id)
        .select_related("program")
        .order_by("pk")
        .first()
    )
    return limit_percent_for_record(record)


def limit_percent_for_enrollment(enrollment) -> int:
    """Yazılışın tələbəsi üçün hədd (``organization_id`` + ``student_id`` FK-larından, JOIN-suz)."""
    return limit_percent_for_student(
        organization_id=getattr(enrollment, "organization_id", None),
        student_id=getattr(enrollment, "student_id", None),
    )


def limit_percent_map_for_students(*, organization_id, student_ids) -> dict:
    """``student_id → hədd`` — TƏK sorğu; qeydsiz tələbə lüğətdə YOXDUR (çağıran defoltu tətbiq edir).

    Seçim qaydası :func:`limit_percent_for_student` ilə birə-bir (İLK pk qeyd).
    """
    ids = {sid for sid in student_ids if sid is not None}
    if organization_id is None or not ids:
        return {}
    result: dict = {}
    rows = (
        StudentAcademicRecord.objects.filter(organization_id=organization_id, student_id__in=ids)
        .select_related("program")
        .order_by("pk")
    )
    for record in rows:
        result.setdefault(record.student_id, limit_percent_for_record(record))
    return result


#: Həddin bu payına çatanda «limitə yaxın» xəbərdarlığı (qrid + «Yekun» tabı eyni nisbət).
WARN_RATIO = Decimal("0.75")


class RowLimit(NamedTuple):
    percent: int
    allowed_hours: Decimal


def near_limit(absence_hours, row_limit: RowLimit, *, frozen: bool, barred: bool) -> bool:
    """«Həddə yaxınlaşır» zolağı — donmuş dilimdə və artıq kəsilmiş sətirdə susur."""
    if frozen or barred or row_limit.allowed_hours <= 0:
        return False
    return Decimal(absence_hours) >= row_limit.allowed_hours * WARN_RATIO


def row_limits(*, organization_id, enrollments, total_hours) -> dict:
    """``student_id → RowLimit`` — qrid / «Yekun» sətirləri üçün (tək sorğu, sətir sayından asılı deyil)."""
    limits = limit_percent_map_for_students(
        organization_id=organization_id, student_ids=[e.student_id for e in enrollments]
    )
    result: dict = {}
    for enrollment in enrollments:
        percent = limits.get(enrollment.student_id, DEFAULT_LIMIT_PERCENT)
        result[enrollment.student_id] = RowLimit(percent, Decimal(total_hours) * Decimal(percent) / Decimal(100))
    return result


def limit_percent_for_offering(offering) -> int:
    """AÇILIŞ-səviyyəli hədd — qrupun İLK (pk) akademik qeydinin proqramı.

    Yalnız başlıq/etiket üçün (müəllim qridinin «limit N q/b» sütunu); tələbə
    üzrə qərar :func:`row_limits` / :func:`limit_percent_for_enrollment`-dədir.
    """
    record = (
        StudentAcademicRecord.objects.filter(organization=offering.organization, group=offering.group)
        .select_related("program")
        .first()
    )
    return limit_percent_for_record(record)


def allowed_absence_hours(offering, lessons, *, limit_percent=None) -> Decimal:
    """Açılış üzrə icazəli qayıb saatı (başlıq); ``limit_percent`` verilibsə təkrar sorğu yoxdur."""
    total_hours = exam_eligibility.lesson_hours_for(offering, lessons)
    if limit_percent is None:
        limit_percent = limit_percent_for_offering(offering)
    return Decimal(total_hours) * Decimal(limit_percent) / Decimal(100)


__all__ = [
    "WARN_RATIO",
    "RowLimit",
    "near_limit",
    "allowed_absence_hours",
    "limit_percent_for_enrollment",
    "limit_percent_for_offering",
    "limit_percent_for_record",
    "limit_percent_for_student",
    "limit_percent_map_for_students",
    "row_limits",
]
