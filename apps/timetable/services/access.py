"""İcazə + əhatə qapıları — ``schedule.manage`` (registrar cədvəl idarəetməsi ilə EYNİ).

Sahib qərarı (2026-09): cədvəli proqram koordinatoru / tyutor / dekanlıq / RİM qurur;
adi müəllimdə açar yoxdur. Hər yoxlama FAIL-CLOSED-dur və struktur əhatəsi
``registrar.schedule_manage`` (``Membership.scope_unit`` alt-ağacı) ilə eynidir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404

from apps.registrar.public import schedule_manage
from core.http_ids import parse_uuid
from core.tenancy import get_request_organization


def organization_for(request):
    """Aktiv təşkilat + ``schedule.manage`` — yoxdursa 403 (fail-closed)."""
    organization = get_request_organization(request)
    if organization is None or not schedule_manage.can_manage(request.user, organization):
        raise PermissionDenied
    return organization


def can_manage(user, organization) -> bool:
    return schedule_manage.can_manage(user, organization)


def scoped_groups(user, organization):
    return schedule_manage.scoped_groups(user, organization)


def period_or_default(organization, raw=""):
    """Seçilmiş semestr (``?period=``) və ya cari/ən yeni semestr."""
    Period = django_apps.get_model("organizations", "AcademicPeriod")
    periods = Period.objects.filter(organization=organization).order_by("-start_date")
    pk = parse_uuid(raw)
    if pk is not None:
        chosen = periods.filter(pk=pk).first()
        if chosen is not None:
            return chosen
    return periods.filter(is_current=True).first() or periods.first()


def period_choices(organization) -> list:
    Period = django_apps.get_model("organizations", "AcademicPeriod")
    return [
        {"value": str(p.pk), "label": f"{p.name} {p.year_display}"}
        for p in Period.objects.filter(organization=organization).order_by("-start_date")[:12]
    ]


def scoped_teacher_ids(user, organization, period) -> set:
    """Aktorun əhatəsindəki açılışların müəllimləri + tapşırıq bölgüsündəki müəllimlər."""
    offerings = schedule_manage.scoped_offerings(user, organization, period=period)
    ids = {pk for pk in offerings.exclude(instructor__isnull=True).values_list("instructor_id", flat=True)}
    try:
        Assignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:
        return ids
    groups = offerings.values("group_id")
    ids |= set(
        Assignment.objects.filter(
            organization=organization, row__period=period, row__groups__in=groups, teacher__isnull=False
        ).values_list("teacher_id", flat=True)
    )
    return ids


def teacher_or_404(user, organization, period, raw):
    """Əhatədəki müəllim — başqa fakültənin müəllimi 404 (varlığı sızmasın)."""
    from django.contrib.auth import get_user_model

    try:
        pk = int(str(raw or "").strip())
    except (TypeError, ValueError):
        raise Http404 from None
    if pk not in scoped_teacher_ids(user, organization, period):
        raise Http404
    teacher = get_user_model().objects.filter(pk=pk).first()
    if teacher is None:
        raise Http404
    return teacher


def run_or_404(request, organization, raw):
    """İşləmə — yalnız aktorun özünün və ya əhatəsindəki (org-wide aktor hamısını görür)."""
    Run = django_apps.get_model("timetable", "TimetableRun")
    pk = parse_uuid(raw)
    if pk is None:
        raise Http404
    run = Run.objects.filter(organization=organization, pk=pk).select_related("period", "created_by").first()
    if run is None or not run_visible(request.user, organization, run):
        raise Http404
    return run


def run_visible(user, organization, run) -> bool:
    """Aktor işləmənin qruplarından ən azı birini idarə edirsə görür (fail-closed)."""
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    if run.created_by_id == getattr(user, "pk", None):
        return True
    group_ids = list(run.slots.values_list("offering__group_id", flat=True).distinct()[:200])
    if not group_ids:
        return False
    return scoped_groups(user, organization).filter(pk__in=group_ids).exists()


def visible_runs(user, organization, period):
    """Siyahı üçün işləmələr: öz yaratdıqları + əhatəsindəki qrupların işləmələri."""
    Run = django_apps.get_model("timetable", "TimetableRun")
    runs = Run.objects.filter(organization=organization, period=period)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return runs
    scope = schedule_manage.actor_scope(user, organization)
    if scope.is_org_wide:
        return runs
    groups = scoped_groups(user, organization).values("pk")
    return runs.filter(Q(created_by=user) | Q(slots__offering__group__in=groups)).distinct()


__all__ = [
    "can_manage",
    "organization_for",
    "period_choices",
    "period_or_default",
    "run_or_404",
    "run_visible",
    "scoped_groups",
    "scoped_teacher_ids",
    "teacher_or_404",
    "visible_runs",
]
