"""Registrar / struktur məlumatına YEGANƏ giriş nöqtəsi (app registry ilə).

MODUL SƏRHƏDİ: ``apps.registrar.models`` birbaşa import EDİLMİR (kontekst
ratchet-i, ``scripts/context_map.py``) — modellər ``django.apps.apps.get_model``
ilə həll olunur və bütün sorğular bu faylda toplanır. Jurnal konteksti gələcəkdə
mikroservisə çıxsa, dəyişəcək tək fayl budur.

«Jurnal bağlıdır» tərifi ``gradebook.journal_is_locked`` ilə EYNİDİR:
``AssessmentScheme.is_published`` və ya ``approval_status='approved'``
(RİM-in toplu bağlaması, ``registrar/journal_close.py``).

«Fənni kim tədris edib»: açılışın dərslərinin ``Lesson.instructor``-u, boşdursa
``CourseOffering.instructor`` (``journal_extras.journal_teaching_summary`` ilə
eyni qayda); dərsi olmayan açılış üçün yalnız açılışın müəllimi.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q
from django.db.models.functions import Coalesce

from core.constants import OrgUnitType

#: Kafedra rolunu daşıyan bölmə tipləri (``syllabus.services.units`` ilə eyni).
CHAIR_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
_DROPPED = "dropped"
_CLOSED_Q = Q(offering__assessment_scheme__is_published=True) | Q(
    offering__assessment_scheme__approval_status="approved"
)


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


# ── Bağlı jurnallar və qeydiyyatlar ──────────────────────────────────────────


def closed_enrollments(organization, period_id, *, student=None):
    """Dövrün DROPPED olmayan, jurnalı BAĞLI qeydiyyatları (queryset)."""
    queryset = (
        _model("registrar", "Enrollment")
        .objects.filter(organization=organization, offering__period_id=period_id)
        .exclude(status=_DROPPED)
        .filter(_CLOSED_Q)
    )
    if student is not None:
        queryset = queryset.filter(student=student)
    return queryset


def closed_offerings(organization, period_id):
    """Dövrün jurnalı bağlı açılışları (queryset)."""
    return (
        _model("registrar", "CourseOffering")
        .objects.filter(organization=organization, period_id=period_id)
        .filter(Q(assessment_scheme__is_published=True) | Q(assessment_scheme__approval_status="approved"))
    )


def student_ids_in_offerings(organization, offering_ids) -> set:
    """Verilmiş açılışlarda (DROPPED olmayan) qeydiyyatı olan tələbələr."""
    rows = (
        _model("registrar", "Enrollment")
        .objects.filter(organization=organization, offering_id__in=offering_ids)
        .exclude(status=_DROPPED)
        .values_list("student_id", flat=True)
        .distinct()
    )
    return set(rows)


def offering_teachers(offering_ids) -> dict:
    """``{offering_id: {teacher_id, …}}`` — dərs müəllimləri, geri düşmə açılışın müəllimi.

    ``offering_ids`` siyahı və ya ``values("pk")`` alt-sorğusu ola bilər (2 sorğu).
    """
    Lesson = _model("registrar", "Lesson")
    CourseOffering = _model("registrar", "CourseOffering")
    result: dict = defaultdict(set)
    rows = (
        Lesson.objects.filter(offering_id__in=offering_ids)
        .annotate(teacher=Coalesce("instructor_id", "offering__instructor_id"))
        .order_by()
        .values_list("offering_id", "teacher")
        .distinct()
    )
    for offering_id, teacher_id in rows:
        if teacher_id:
            result[offering_id].add(teacher_id)
    for offering_id, instructor_id in (
        CourseOffering.objects.filter(pk__in=offering_ids)
        .exclude(pk__in=list(result))
        .values_list("pk", "instructor_id")
    ):
        if instructor_id:
            result[offering_id].add(instructor_id)
    return dict(result)


# ── Struktur: müəllimin kafedrası, fakültə ──────────────────────────────────


def teacher_chair_units(organization, teacher_ids) -> dict:
    """``{teacher_id: chair_unit_id}`` — müəllimin AKTİV kafedra üzvlüyü (əsas birinci)."""
    teacher_ids = [pk for pk in set(teacher_ids) if pk]
    if not teacher_ids:
        return {}
    rows = (
        _model("organizations", "Membership")
        .objects.filter(
            organization=organization,
            user_id__in=teacher_ids,
            is_active=True,
            scope_unit__unit_type__in=CHAIR_UNIT_TYPES,
        )
        .order_by("user_id", "-is_primary", "pk")
        .values_list("user_id", "scope_unit_id")
    )
    result: dict = {}
    for user_id, unit_id in rows:
        result.setdefault(user_id, unit_id)
    return result


def resolve_departments(organization, pairs) -> dict:
    """``{(offering_id, teacher_id): chair_unit_id | None}``.

    Sıra: müəllimin kafedra üzvlüyü → fənnin sahib kafedrası (``Subject.chair_unit``).
    """
    pairs = list(pairs)
    if not pairs:
        return {}
    by_teacher = teacher_chair_units(organization, [teacher for _offering, teacher in pairs])
    need_subject = [offering for offering, teacher in pairs if teacher not in by_teacher]
    by_offering = {}
    if need_subject:
        by_offering = dict(
            _model("registrar", "CourseOffering")
            .objects.filter(pk__in=set(need_subject))
            .values_list("pk", "subject__chair_unit_id")
        )
    return {(offering, teacher): by_teacher.get(teacher) or by_offering.get(offering) for offering, teacher in pairs}


def unit_paths(unit_ids) -> dict:
    unit_ids = [pk for pk in set(unit_ids) if pk]
    if not unit_ids:
        return {}
    return dict(_model("organizations", "OrgUnit").objects.filter(pk__in=unit_ids).values_list("pk", "path"))


def faculties_for_units(unit_ids) -> dict:
    """``{unit_id: faculty_id | None}`` — ən yaxın ``faculty`` əcdadı (path ilə, 2 sorğu)."""
    paths = unit_paths(unit_ids)
    segments = {unit_id: [seg for seg in (path or "").strip("/").split("/") if seg] for unit_id, path in paths.items()}
    ancestor_ids = {seg for segs in segments.values() for seg in segs}
    faculties = set()
    if ancestor_ids:
        faculties = {
            str(pk)
            for pk in _model("organizations", "OrgUnit")
            .objects.filter(pk__in=ancestor_ids, unit_type=OrgUnitType.FACULTY)
            .values_list("pk", flat=True)
        }
    result = {}
    for unit_id, segs in segments.items():
        found = next((seg for seg in reversed(segs) if seg in faculties), None)
        result[unit_id] = uuid.UUID(found) if found else None
    return result


def group_course_year(group_settings) -> int | None:
    raw = group_settings.get("course_year") if isinstance(group_settings, dict) else None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 10 else None


# ── Cavab snapshot-u (yalnız açılış/müəllim/struktur atributları) ────────────


def offering_snapshot(organization, offering_id, teacher_id) -> dict:
    """Müəllim bölməsi cavabının analitika sahələri — TƏLƏBƏYƏ aid atribut YOXDUR."""
    offering = (
        _model("registrar", "CourseOffering")
        .objects.filter(organization=organization, pk=offering_id)
        .select_related("group")
        .only("pk", "subject_id", "group_id", "group__settings", "group__parent_id")
        .first()
    )
    if offering is None:
        return {}
    department_id = resolve_departments(organization, [(offering.pk, teacher_id)]).get((offering.pk, teacher_id))
    faculty_id = faculties_for_units([department_id]).get(department_id) if department_id else None
    program_id = None
    course_year = None
    if offering.group_id:
        course_year = group_course_year(offering.group.settings)
        if offering.group.parent_id:
            program_id = (
                _model("registrar", "Program")
                .objects.filter(organization=organization, specialty_unit_id=offering.group.parent_id)
                .values_list("pk", flat=True)
                .first()
            )
    return {
        "subject_id": offering.subject_id,
        "group_id": offering.group_id,
        "teacher_department_id": department_id,
        "faculty_id": faculty_id,
        "program_id": program_id,
        "course_year": course_year,
    }


def student_snapshot(organization, student) -> dict:
    """Ümumi bölmə cavabının analitika sahələri — tələbənin aktiv qrupu/ixtisası."""
    record = (
        _model("registrar", "StudentAcademicRecord")
        .objects.filter(organization=organization, student=student, is_active=True)
        .select_related("group")
        .only("pk", "program_id", "group_id", "group__settings", "group__path")
        .order_by("-created_at")
        .first()
    )
    if record is None:
        return {}
    faculty_id = faculties_for_units([record.group_id]).get(record.group_id) if record.group_id else None
    return {
        "group_id": record.group_id,
        "program_id": record.program_id,
        "faculty_id": faculty_id,
        "course_year": group_course_year(record.group.settings) if record.group_id else None,
    }


def offering_labels(offering_ids) -> dict:
    """``{offering_id: {"subject": ad, "subject_code": kod, "group": ad}}`` (tək sorğu)."""
    rows = (
        _model("registrar", "CourseOffering")
        .objects.filter(pk__in=offering_ids)
        .values_list("pk", "subject__name", "subject__code", "group__name")
    )
    return {pk: {"subject": name, "subject_code": code, "group": group or ""} for pk, name, code, group in rows}
