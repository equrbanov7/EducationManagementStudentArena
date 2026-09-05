"""Tapşırıq və sətir əməliyyatları (yaratma, redaktə, silmə, validasiya)."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from ..constants import (
    EDITABLE_STATUSES,
    TOTAL_HOUR_FIELDS,
    DegreeLevel,
    EducationForm,
    RowKind,
    Season,
    TaskStatus,
)
from ..models import TeachingTask, TeachingTaskRow
from .people import resolve_chair
from .scoping import WorkloadDenied, ensure_can_manage

#: Sətirdə birbaşa yazıla bilən skalyar sahələr (view qatı bunları filtrləyir).
ROW_SCALAR_FIELDS = (
    "season",
    "row_kind",
    "subject_text",
    "specialty_text",
    "groups_text",
    "education_form",
    "degree_level",
    "student_count",
    "student_count_text",
    "union_count",
    "subgroup_count",
    "lecture_plan",
    "lecture_total",
    "seminar_plan",
    "seminar_total",
    "lab_plan",
    "lab_total",
    "consult_hours",
    "exam_hours",
    "thesis_hours",
    "postgrad_hours",
    "practice_research_hours",
    "practice_production_hours",
    "credits",
    "credits_value",
    "note",
    "order",
)

_CHOICE_FIELDS = {
    "season": {value for value, _ in Season.choices},
    "row_kind": {value for value, _ in RowKind.choices},
    "education_form": {value for value, _ in EducationForm.choices},
    "degree_level": {value for value, _ in DegreeLevel.choices},
}

_INT_FIELDS = {
    "student_count",
    "union_count",
    "subgroup_count",
    "lecture_plan",
    "lecture_total",
    "seminar_plan",
    "seminar_total",
    "lab_plan",
    "lab_total",
    "consult_hours",
    "exam_hours",
    "thesis_hours",
    "postgrad_hours",
    "practice_research_hours",
    "practice_production_hours",
    "credits_value",
    "order",
}


def normalize_academic_year(raw: str) -> str:
    """«2026», «2026-2027», «2026/2027» → «2026/2027» (AcademicPeriod konvensiyası).

    Yalnız formatlayırdı — `year='abc'` ilə tapşırıq yaranırdı (QA 2026-09-05
    WORKLOAD-SCHEDULE-02). İndi «YYYY/YYYY+1» nümunəsi tələb olunur; uyğunsuz → boş.
    """
    import re

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    year = AcademicPeriod.format_year(raw) or ""
    match = re.fullmatch(r"(\d{4})/(\d{4})", year)
    if not match or int(match.group(2)) != int(match.group(1)) + 1 or not 2000 <= int(match.group(1)) <= 2100:
        return ""
    return year


# ── Tapşırıq ────────────────────────────────────────────────────────────────


def get_or_create_task(*, organization, chair_id, academic_year: str, actor, request=None):
    """Kafedra + il üçün tapşırıq (yoxdursa yaradılır). Kafedra müdiri / RİM."""
    chair = resolve_chair(organization, chair_id)  # UUID qapısı burada (WORKLOAD-SCHEDULE-01)
    ensure_can_manage(actor, chair.pk)
    year = normalize_academic_year(academic_year)
    if not year:
        raise WorkloadDenied("workload.year_required", "Tədris ili göstərilməlidir.")
    task, created = TeachingTask.objects.get_or_create(
        organization=organization,
        chair=chair,
        academic_year=year,
        defaults={"created_by": getattr(actor, "user", None), "status": TaskStatus.DRAFT},
    )
    if created:
        log_action(
            AuditAction.CREATE,
            user=getattr(actor, "user", None),
            organization=organization,
            obj=task,
            new_values={"academic_year": year, "chair": str(chair.pk), "status": task.status},
            reason="workload.task_created",
            request=request,
            resource_type="workload.TeachingTask",
            resource_id=str(task.pk),
            resource_repr=f"{chair.name} · {year}",
        )
    return task, created


def find_task(*, organization, chair_id, academic_year: str):
    return (
        TeachingTask.objects.filter(
            organization=organization,
            chair_id=chair_id,
            academic_year=normalize_academic_year(academic_year),
        )
        .select_related("chair")
        .first()
    )


def list_years(*, organization, chair_ids=None) -> list[str]:
    qs = TeachingTask.objects.filter(organization=organization)
    if chair_ids is not None:
        qs = qs.filter(chair_id__in=list(chair_ids))
    return sorted({row for row in qs.values_list("academic_year", flat=True)}, reverse=True)


# ── Sətir validasiyası ──────────────────────────────────────────────────────


def _coerce(field: str, value):
    if field in _INT_FIELDS:
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise WorkloadDenied("workload.invalid_number", f"«{field}» rəqəm olmalıdır.")
        if number < 0:
            raise WorkloadDenied("workload.negative_number", f"«{field}» mənfi ola bilməz.")
        return number
    if field in _CHOICE_FIELDS:
        text = str(value or "").strip()
        if text not in _CHOICE_FIELDS[field]:
            raise WorkloadDenied("workload.invalid_choice", f"«{field}» üçün yanlış dəyər.")
        return text
    return str(value or "").strip()


def row_warnings(row: TeachingTaskRow) -> list[dict]:
    """BLOKLAMAYAN xəbərdarlıqlar (spec §5.2: real fayllarda kənarlaşmalar var)."""
    warnings: list[dict] = []
    expected_lecture = int(row.lecture_plan or 0) * int(row.union_count or 0)
    if row.lecture_plan and row.lecture_total != expected_lecture:
        warnings.append({"code": "lecture_total_mismatch", "expected": expected_lecture})
    expected_seminar = int(row.seminar_plan or 0) * int(row.subgroup_count or 0)
    if row.seminar_plan and row.seminar_total != expected_seminar:
        warnings.append({"code": "seminar_total_mismatch", "expected": expected_seminar})
    expected_lab = int(row.lab_plan or 0) * int(row.subgroup_count or 0)
    if row.lab_plan and row.lab_total != expected_lab:
        warnings.append({"code": "lab_total_mismatch", "expected": expected_lab})
    computed = row.computed_total_hours
    if row.total_hours != computed:
        warnings.append({"code": "total_hours_mismatch", "expected": computed})
    if row.specialty_id and row.pk:
        specialty = row.specialty
        outside = [
            group.name
            for group in row.groups.all()
            if specialty and not (group.path or "").startswith(f"{specialty.path}/")
        ]
        if outside:
            warnings.append({"code": "group_specialty_mismatch", "groups": outside})
    return warnings


def resolve_specialty_and_faculty(organization, specialty_id):
    """İxtisas ``OrgUnit`` + onun fakültəsi (path ilə yuxarı gedərək)."""
    if not specialty_id:
        return None, None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    specialty = OrgUnit.objects.filter(organization=organization, pk=specialty_id).first()
    if specialty is None:
        return None, None
    ancestor_ids = [part for part in (specialty.path or "").split("/") if part][:-1]
    faculty = (
        OrgUnit.objects.filter(organization=organization, pk__in=ancestor_ids, unit_type=OrgUnitType.FACULTY).first()
        if ancestor_ids
        else None
    )
    return specialty, faculty


def _ensure_editable(task: TeachingTask) -> None:
    if task.status not in EDITABLE_STATUSES:
        raise WorkloadDenied(
            "workload.task_not_editable",
            "Bu statusda sətir dəyişmək olmaz — düzəliş axını (amendment) istifadə edilməlidir.",
        )


def _duplicate_row_exists(row: TeachingTaskRow) -> bool:
    """Eyni fənn + ixtisas + semestr + QRUP DƏSTİ ilə ikinci sətir varmı (QA P2-37).

    Qruplar M2M olduğu üçün müqayisə sətir yaddaşa yazılıb qruplar təyin
    ediləndən SONRA aparılır; `save_row` atomik olduğuna görə tapılan dublikat
    yazını geri qaytarır.
    """
    others = TeachingTaskRow.objects.filter(
        task=row.task,
        season=row.season,
        specialty_id=row.specialty_id,
    ).exclude(pk=row.pk)
    if row.subject_id:
        others = others.filter(subject_id=row.subject_id)
    else:
        others = others.filter(subject_id__isnull=True, subject_text__iexact=(row.subject_text or "").strip())
    wanted = set(row.groups.values_list("id", flat=True))
    for other in others.prefetch_related("groups"):
        if set(other.groups.values_list("id", flat=True)) == wanted:
            return True
    return False


@transaction.atomic
def save_row(*, task: TeachingTask, actor, data: dict, row=None, request=None) -> TeachingTaskRow:
    """Sətir yaradır və ya redaktə edir (draft/distributing statuslarında)."""
    ensure_can_manage(actor, task.chair_id)
    _ensure_editable(task)

    row = row or TeachingTaskRow(organization=task.organization, task=task)
    if row.pk and row.task_id != task.pk:
        raise WorkloadDenied("workload.row_foreign", "Sətir bu tapşırığa aid deyil.")
    old_values = {field: getattr(row, field) for field in TOTAL_HOUR_FIELDS + ("total_hours",)} if row.pk else None

    for field in ROW_SCALAR_FIELDS:
        if field in data:
            setattr(row, field, _coerce(field, data[field]))

    if "subject_id" in data:
        subject_id = data.get("subject_id") or None
        if subject_id:
            Subject = django_apps.get_model("registrar", "Subject")
            subject = Subject.objects.filter(organization=task.organization, pk=subject_id).first()
            if subject is None:
                raise WorkloadDenied("workload.subject_not_found", "Fənn tapılmadı.")
            row.subject = subject
            if not row.subject_text:
                row.subject_text = subject.name
        else:
            row.subject = None

    if "period_id" in data:
        period_id = data.get("period_id") or None
        if period_id:
            AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
            period = AcademicPeriod.objects.filter(organization=task.organization, pk=period_id).first()
            if period is None:
                raise WorkloadDenied("workload.period_not_found", "Semestr tapılmadı.")
            row.period = period
        else:
            row.period = None

    if "specialty_id" in data:
        specialty, faculty = resolve_specialty_and_faculty(task.organization, data.get("specialty_id") or None)
        row.specialty = specialty
        row.faculty = faculty

    if not (row.subject_id or row.subject_text):
        raise WorkloadDenied("workload.subject_required", "Fənn adı və ya kataloq fənni göstərilməlidir.")

    # `total_hours` DB-də saxlanılır (rəsmi Excel-in «CƏMİ» sütunu); əl ilə
    # verilməyibsə cəmilərin cəmindən hesablanır — fərq varsa xəbərdarlıq
    # (`row_warnings`) çıxır, amma BLOKLANMIR.
    manual_total = data.get("total_hours")
    row.total_hours = _coerce("student_count", manual_total) if manual_total else row.computed_total_hours
    row.save()

    if "group_ids" in data:
        group_ids = [gid for gid in (data.get("group_ids") or []) if gid]
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        groups = list(
            OrgUnit.objects.filter(organization=task.organization, pk__in=group_ids, unit_type=OrgUnitType.GROUP)
        )
        row.groups.set(groups)
        if not row.groups_text:
            row.groups_text = " / ".join(group.name for group in groups)
            row.save(update_fields=["groups_text", "updated_at"])

    if _duplicate_row_exists(row):
        raise WorkloadDenied(
            "workload.duplicate_row",
            "Eyni fənn, ixtisas, semestr və qrup dəsti ilə sətir artıq var — mövcud sətri redaktə edin.",
        )

    log_action(
        AuditAction.UPDATE if old_values else AuditAction.CREATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=row,
        old_values=old_values,
        new_values={"total_hours": row.total_hours, "subject": row.subject_label},
        reason="workload.row_saved",
        request=request,
        resource_type="workload.TeachingTaskRow",
        resource_id=str(row.pk),
        resource_repr=row.subject_label,
    )
    return row


@transaction.atomic
def delete_row(*, task: TeachingTask, row: TeachingTaskRow, actor, request=None) -> None:
    ensure_can_manage(actor, task.chair_id)
    _ensure_editable(task)
    if row.task_id != task.pk:
        raise WorkloadDenied("workload.row_foreign", "Sətir bu tapşırığa aid deyil.")
    label = row.subject_label
    row_id = str(row.pk)
    row.delete()
    log_action(
        AuditAction.DELETE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        reason="workload.row_deleted",
        request=request,
        resource_type="workload.TeachingTaskRow",
        resource_id=row_id,
        resource_repr=label,
    )


__all__ = [
    "ROW_SCALAR_FIELDS",
    "delete_row",
    "find_task",
    "get_or_create_task",
    "list_years",
    "normalize_academic_year",
    "resolve_specialty_and_faculty",
    "row_warnings",
    "save_row",
]
