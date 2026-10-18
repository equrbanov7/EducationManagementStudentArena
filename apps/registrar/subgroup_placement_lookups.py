"""«Alt qrupa tələbə əlavə et» alətinin AXTARIŞ və XÜLASƏ sorğuları (oxu-only, 2026-10-18).

Alət (accounts) registrar modellərini birbaşa import etmir — bütün sorğular buradadır və əhatə
(:mod:`apps.registrar.subgroup_access`) burada tətbiq olunur. Axtarışlar ``EMSSearchableSelect`` müqaviləsinə
uyğun ``{"results": [{"id", "text", "hint", "disabled"}], "has_more"}`` qaytarır; səhifələmə ``offset``/``limit``.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.search_text import tolerant_q

from . import credit_load
from . import subgroup_access as access
from . import subgroup_placement_errors as errors
from . import subgroup_placement_history as history
from . import subgroup_placement_query as query
from .models import AcademicStatus, CourseOffering, Enrollment, StudentAcademicRecord, Subject

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def current_period(organization):
    """Təşkilatın CARİ, aktiv dövrü (yerləşdirmə yalnız orada mümkündür); yoxdursa ``None``."""
    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    return period_model.objects.filter(organization=organization, is_current=True, is_active=True).first()


def _bounds(offset, limit):
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(limit or PAGE_SIZE)
    except (TypeError, ValueError):
        limit = PAGE_SIZE
    return offset, max(1, min(limit, MAX_PAGE_SIZE))


def _name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _records(actor, organization):
    queryset = StudentAcademicRecord.objects.filter(
        organization=organization, is_active=True, status=AcademicStatus.ENROLLED, group__isnull=False
    )
    if not access.is_org_wide(actor, organization):
        queryset = queryset.filter(group__in=access.scoped_groups(actor, organization))
    return queryset


def search_students(*, actor, organization, q="", offset=0, limit=PAGE_SIZE) -> dict:
    """Aktorun əhatəsindəki oxuyan tələbələr (ad, soyad, istifadəçi adı, qrup)."""
    offset, limit = _bounds(offset, limit)
    queryset = _records(actor, organization)
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
    seen: set = set()
    results = []
    for record in window[:limit]:
        if record.student_id in seen:
            continue
        seen.add(record.student_id)
        results.append(
            {
                "id": str(record.student_id),
                # Adaşlar qrupla ayırd edilsin («Əli Məmmədov · 234 K2»).
                "text": f"{_name(record.student)} · {getattr(record.group, 'name', '')}",
                "hint": getattr(record.group, "name", ""),
            }
        )
    return {"results": results, "has_more": len(window) > limit}


def resolve_student(*, actor, organization, student_id):
    """``(student, record)`` — əhatədəki oxuyan tələbə; yoxdursa ``OUT_OF_SCOPE`` (HTTP 404)."""
    try:
        student_id = int(str(student_id))
    except (TypeError, ValueError):
        raise errors.SubgroupPlacementError(errors.OUT_OF_SCOPE)
    record = (
        _records(actor, organization)
        .filter(student_id=student_id)
        .select_related("student", "group", "program", "curriculum")
        .order_by("-created_at")
        .first()
    )
    if record is None:
        raise errors.SubgroupPlacementError(errors.OUT_OF_SCOPE)
    return record.student, record


def student_summary(*, actor, organization, student_id) -> dict:
    """Addım 1: tələbənin qrupu, kredit yükü, kəsilmiş fənləri və yerləşdirmə tarixçəsi."""
    student, record = resolve_student(actor=actor, organization=organization, student_id=student_id)
    period = current_period(organization)
    load = credit_load.credit_load(student, period, organization=organization, record=record)
    outcomes = query.subject_outcomes(
        student=student, organization=organization, exclude_period_id=getattr(period, "pk", None)
    )
    return {
        "student_id": str(student.pk),
        "name": _name(student),
        "username": student.username,
        "group": getattr(record.group, "name", "") or "",
        "program": record.program.display_label,
        "period": f"{period.year_display} · {period.name}" if period else "",
        "has_period": period is not None,
        "credit": {key: load[key] for key in ("total", "own", "subgroup", "limit", "remaining", "base_limit",
                                              "subgroup_limit", "over_limit")},
        "subjects": load["items"],
        "failed": query.failed_subjects(outcomes),
        "placements": history.student_placements(student=student, organization=organization),
    }  # fmt: skip


def search_subjects(*, actor, organization, student_id, q="", offset=0, limit=PAGE_SIZE) -> dict:
    """Addım 2: bu semestr BAŞQA qruplarda aktiv jurnalı olan fənlər (kəsilmişlər işarələnir)."""
    from django.utils.translation import pgettext

    student, record = resolve_student(actor=actor, organization=organization, student_id=student_id)
    period = current_period(organization)
    offset, limit = _bounds(offset, limit)
    if period is None:
        return {"results": [], "has_more": False}
    offered = CourseOffering.objects.filter(organization=organization, period=period, is_active=True).exclude(
        group_id=record.group_id
    )
    queryset = Subject.objects.filter(organization=organization, pk__in=offered.values("subject_id"))
    search = tolerant_q(q, ("name",), compact_fields=("code",))
    if search is not None:
        queryset = queryset.filter(search)
    window = list(queryset.order_by("name", "code")[offset : offset + limit + 1])
    page = window[:limit]
    ids = [subject.pk for subject in page]
    enrolled = set(
        Enrollment.objects.filter(
            organization=organization,
            student=student,
            offering__period=period,
            offering__subject_id__in=ids,
            status=Enrollment.Status.ENROLLED,
        )
        .exclude(offering__group_id=record.group_id)
        .values_list("offering__subject_id", flat=True)
    )
    outcomes = query.subject_outcomes(
        student=student, organization=organization, exclude_period_id=period.pk, subject_ids=ids
    )
    failed_hint = pgettext("registrar.subgroup_placement", "kəsilib")
    passed_hint = pgettext("registrar.subgroup_placement", "keçib")
    enrolled_hint = pgettext("registrar.subgroup_placement", "artıq alt qrupdadır")
    results = []
    for subject in page:
        outcome = outcomes.get(subject.pk) or {}
        hint = (
            enrolled_hint
            if subject.pk in enrolled
            else (failed_hint if outcome.get("failed") else (passed_hint if outcome.get("passed") else ""))
        )
        results.append(
            {
                "id": str(subject.pk),
                "text": f"{subject.name} · {subject.code}",
                "hint": hint,
                "disabled": subject.pk in enrolled or bool(outcome.get("passed")),
                "failed": bool(outcome.get("failed")),
            }
        )
    return {"results": results, "has_more": len(window) > limit}


def offerings_for(*, actor, organization, student_id, subject_id) -> dict:
    """Addım 2 (davamı): fənnin uyğun jurnalları — müəllim, cədvəl, tutum, kredit təsiri, toqquşma."""
    from core import runtime_settings

    student, record = resolve_student(actor=actor, organization=organization, student_id=student_id)
    period = current_period(organization)
    subject = Subject.objects.filter(organization=organization, pk=subject_id).first() if subject_id else None
    if subject is None or period is None:
        return {"subject": None, "offerings": []}
    rows = query.candidate_offerings(
        organization=organization,
        student=student,
        record=record,
        subject_id=subject.pk,
        period=period,
        capacity=runtime_settings.get_int("credits.journal_capacity"),
    )
    load = credit_load.credit_load(student, period, organization=organization, record=record)
    for row in rows:
        released = row["credits"] if row["releases_own"] else 0
        row["projection"] = credit_load.projected(load, add_credits=row["credits"], release_credits=released)
    return {"subject": {"id": str(subject.pk), "name": subject.name, "code": subject.code}, "offerings": rows}


def offering_for(*, organization, offering_id):
    """Yerləşdirmə üçün açılış (təşkilat daxilində); yoxdursa ``NOT_FOUND``."""
    offering = (
        CourseOffering.objects.filter(organization=organization, pk=offering_id)
        .select_related("subject", "period", "group", "organization", "instructor")
        .first()
        if offering_id
        else None
    )
    if offering is None:
        raise errors.SubgroupPlacementError(errors.NOT_FOUND)
    return offering


def preview(*, actor, organization, student_id, offering_id, release_source=False) -> dict:
    """Təsdiqdən ƏVVƏL bütün yoxlamalar (yazı yoxdur) — JSON-a hazır."""
    from .subgroup_placement import evaluate

    student, record = resolve_student(actor=actor, organization=organization, student_id=student_id)
    offering = offering_for(organization=organization, offering_id=offering_id)
    plan = evaluate(student=student, offering=offering, actor=actor, release_source=release_source, record=record)
    credit = plan.get("credit") or {}
    return {
        "ok": plan["ok"],
        "errors": plan["errors"],
        "warnings": plan["warnings"],
        "clashes": plan["clashes"],
        "retake": plan["retake"],
        "credits": plan["credits"],
        "projection": credit.get("projection"),
        "conflicts": [
            {"group": getattr(row.offering.group, "name", "") or "", "subject": row.offering.subject.name}
            for row in plan["conflicts"]
        ],
        "offering": {
            "id": str(offering.pk),
            "subject": offering.subject.name,
            "group": getattr(offering.group, "name", "") or "",
        },
    }


__all__ = [
    "current_period",
    "offering_for",
    "offerings_for",
    "preview",
    "resolve_student",
    "search_students",
    "search_subjects",
    "student_summary",
]
