"""Proqram məktəbi və kafedra yönləndirməsi: yalnız təsdiqli struktur bağlantıları."""

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError

from apps.organizations.public import resolve_ancestor
from core.constants import OrgUnitType

from ..state_machine import TransitionDenied


def program_unit_for(user, organization):
    """Aktiv akademik qeyddəki proqram; ad oxşarlığı ilə uyğunluq axtarılmır."""
    cache = getattr(user, "_applications_program_scope", None)
    if cache is not None and cache[0] == organization.pk:
        return cache[1]
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    record = (
        Record.objects.filter(organization=organization, student=user, is_active=True)
        .select_related("program__specialty_unit")
        .order_by("-created_at")
        .first()
    )
    unit = record.program.specialty_unit if record and record.program.specialty_unit_id else None
    if unit is not None and unit.organization_id != organization.pk:
        unit = None
    user._applications_program_scope = (organization.pk, unit)
    return unit


def applicant_unit(application):
    if application.sender_family == "student":
        return program_unit_for(application.created_by, application.organization) or application.sender_scope_unit
    return application.sender_scope_unit


def chair_choices(application):
    """Ağacda kafedra yoxdursa məktəbin aktiv kafedraları açıq seçimə çıxır."""
    Unit = django_apps.get_model("organizations", "OrgUnit")
    school = resolve_ancestor(applicant_unit(application), OrgUnitType.FACULTY)
    if school is None:
        return Unit.objects.none()
    return Unit.objects.filter(
        organization_id=application.organization_id,
        is_active=True,
        unit_type__in=[OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT],
        path__startswith=school.path + "/",
    ).order_by("name")


def forward_scope(application, target_unit, scope_id=None):
    from .routing import resolve_scope_unit

    scope = resolve_scope_unit(target_unit, applicant_unit(application))
    if target_unit.resolve_by != "chair":
        if scope_id:
            raise TransitionDenied("scope.invalid", "Bu şöbə üçün kafedra seçimi qəbul edilmir.")
        return scope
    if scope is not None and not scope_id:
        return scope
    try:
        selected = chair_choices(application).filter(pk=scope_id).first() if scope_id else None
    except (ValueError, TypeError, ValidationError):
        selected = None
    if selected is None:
        raise TransitionDenied("scope.required", "Tələbənin məktəbinə aid kafedranı seçin.")
    return selected
