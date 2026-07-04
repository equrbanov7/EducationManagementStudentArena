"""Paylaşılan səhifə kontekstləri (U12) — standalone səhifə + profil bölməsi.

Registrar səhifələrinin (jurnal siyahısı, dərs cədvəli, akademik təqvim,
qiymət təsdiqləri, analitika) kontekst-qurucuları burada yaşayır ki, eyni data
HƏM `/jurnal/...` standalone görünüşlərində, HƏM DƏ profil kabinetinin sağ
panelində (``?section=...``) istifadə olunsun — kod dublikasiyası yoxdur.

``embedded=True`` rejimində naviqasiya linkləri profil shell-inin içində qalır
(``/accounts/profile/?section=X&...``) — istifadəçi sidebar-ı itirmir.
Performans: hər kontekst yalnız aktiv bölmə üçün qurulur (lazy, stage4 gating).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from apps.registrar import analytics, approval, schedule
from apps.registrar.models import ApprovalStatus, AssessmentScheme, CourseOffering, StudentAcademicRecord


def _profile_section_prefix(section: str) -> str:
    return f"{reverse('accounts:profile')}?section={section}&"


def journal_list_context(user) -> dict:
    """The teacher's own offerings — entry points into each journal."""
    offerings = (
        CourseOffering.objects.filter(instructor=user, is_active=True)
        .select_related("subject", "period", "group")
        .order_by("-period__start_date", "subject__code")
    )
    return {"offerings": offerings}


def calendar_context(organization) -> dict:
    """Semesters with registration/exam-session window states."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    today = timezone.localdate()
    periods = [
        {
            "period": period,
            "is_running": period.start_date <= today <= period.end_date,
            "registration_state": period.registration_state,
            "exam_session_state": period.exam_session_state,
        }
        for period in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")
    ]
    return {"has_context": True, "periods": periods, "today": today}


def approvals_context(user, organization) -> dict:
    """Chair/dean inbox: journals awaiting the current user's approval step."""
    statuses = []
    if approval.can_chair_approve(user, organization):
        statuses.append(ApprovalStatus.SUBMITTED)
    if approval.can_dean_approve(user, organization):
        statuses.append(ApprovalStatus.CHAIR_APPROVED)
    schemes = (
        AssessmentScheme.objects.filter(organization=organization, approval_status__in=statuses)
        .select_related("offering__subject", "offering__group", "offering__period", "offering__instructor")
        .order_by("offering__subject__code")
        if statuses
        else AssessmentScheme.objects.none()
    )
    return {"has_context": True, "schemes": schemes, "is_approver": bool(statuses)}


def analytics_context(request, organization, *, embedded=False) -> dict:
    """Analytics dashboard: period picker + batched aggregation."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    periods = list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"))

    requested = (request.GET.get("period") or "").strip()
    period = None
    if requested:
        period = next((p for p in periods if str(p.id) == requested), None)
    if period is None:
        period = next((p for p in periods if p.is_current), periods[0] if periods else None)

    data = (
        analytics.build_period_analytics(organization=organization, period=period)
        if period is not None
        else {"has_data": False, "period": None, "totals": None, "programs": [], "groups": [], "at_risk": []}
    )
    return {"periods": periods, "analytics": data, "analytics_embedded": embedded}


def schedule_context(request, organization, *, embedded=False) -> dict:
    """Role-aware weekly timetable context (student group / teacher own slots)."""
    from apps.registrar.models import WeekType

    period = _current_period(organization)
    try:
        week_offset = max(-8, min(16, int(request.GET.get("w") or 0)))
    except (TypeError, ValueError):
        week_offset = 0
    week_context = schedule.build_week_context(period, offset=week_offset)

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("group")
        .first()
    )
    teacher_offerings = []
    exam_author = None
    course_ids = []
    if record and record.group and period:
        role = "student"
        owner_label = record.group.name
        slots = schedule.get_group_schedule(organization=organization, group=record.group, period=period)
        course_ids = list(
            CourseOffering.objects.filter(organization=organization, group=record.group, period=period).values_list(
                "course_id", flat=True
            )
        )
    else:
        role = "teacher"
        owner_label = request.user.get_full_name() or request.user.username
        exam_author = request.user
        if period:
            slots = schedule.get_teacher_schedule(organization=organization, teacher=request.user, period=period)
            teacher_offerings = list(
                CourseOffering.objects.filter(
                    organization=organization, instructor=request.user, period=period, is_active=True
                ).select_related("subject", "group")
            )
            course_ids = [off.course_id for off in teacher_offerings]
        else:
            slots = []

    exams_by_day = schedule.get_week_exams(
        organization=organization,
        course_ids=course_ids,
        monday=week_context["monday"],
        author=exam_author,
    )

    # Həftə naviqasiyası: standalone-da `?w=N`, profil panelində shell daxilində qalır.
    nav_prefix = _profile_section_prefix("my-schedule") if embedded else "?"
    return {
        "has_context": True,
        "role": role,
        "owner_label": owner_label,
        "period": period,
        "week": week_context,
        "week_days": schedule.build_week_view(slots, week_context=week_context, exams_by_day=exams_by_day),
        "teacher_offerings": teacher_offerings,
        "weekdays": schedule.WEEKDAYS,
        "week_types": WeekType.choices,
        "schedule_nav_prefix": nav_prefix,
        "schedule_embedded": embedded,
    }


def _current_period(organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )
