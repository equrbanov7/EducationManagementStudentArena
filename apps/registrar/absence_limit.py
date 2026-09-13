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

``gradebook.absence_limit_percent_for(offering)`` müəllim qridi üçün qalır
(açılış-səviyyəli «icazəli saat» sütunu); imtahan qapısı və tələbə
səthləri artıq onu çağırmır.
"""

from __future__ import annotations

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


__all__ = ["limit_percent_for_enrollment", "limit_percent_for_record", "limit_percent_for_student"]
