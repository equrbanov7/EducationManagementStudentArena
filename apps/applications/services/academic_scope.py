"""Proqram məktəbi və kafedra yönləndirməsi: yalnız təsdiqli struktur bağlantıları."""

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Case, Q, Value, When

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


def _school_of(application):
    return resolve_ancestor(applicant_unit(application), OrgUnitType.FACULTY)


def _overseer(user, application) -> bool:
    """RİM (nəzarətçi) istənilən məktəbin kafedrasına yönləndirə bilir (MR-000302, sahib 2026-11-12)."""
    if user is None:
        return False
    from .access import can_oversee

    return can_oversee(user, application.organization)


def chair_choices(application, user=None):
    """Kafedra seçimi: adi emalçıya yalnız tələbənin məktəbi, RİM-ə təşkilatın bütün aktiv kafedraları.

    RİM üçün məktəbin öz kafedraları əvvəldə gəlir (``own_school`` annotasiyası), qalanları sonra.
    """
    Unit = django_apps.get_model("organizations", "OrgUnit")
    school = _school_of(application)
    units = Unit.objects.filter(
        organization_id=application.organization_id,
        is_active=True,
        unit_type__in=[OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT],
    )
    own = Q(path__startswith=school.path + "/") if school is not None else None
    if _overseer(user, application):
        flag = (
            Case(When(own, then=Value(True)), default=Value(False), output_field=BooleanField())
            if own is not None
            else Value(False, output_field=BooleanField())
        )
        return units.annotate(own_school=flag).order_by("-own_school", "name")
    if own is None:
        return Unit.objects.none()
    return units.filter(own).annotate(own_school=Value(True, output_field=BooleanField())).order_by("name")


#: Sahib 2026-11-17: kafedra kimi dekanlığa da yönləndirəndə MƏKTƏB (dekanlıq) seçilir.
DEAN_OFFICE_CODE = "dekan"


def school_choices(application, user=None):
    """Dekanlıq seçimi: adi emalçıya yalnız müraciət edənin məktəbi, RİM-ə bütün aktiv məktəblər (öz məktəbi əvvəldə)."""
    Unit = django_apps.get_model("organizations", "OrgUnit")
    school = _school_of(application)
    units = Unit.objects.filter(
        organization_id=application.organization_id, is_active=True, unit_type=OrgUnitType.FACULTY
    )
    if _overseer(user, application):
        flag = (
            Case(When(pk=school.pk, then=Value(True)), default=Value(False), output_field=BooleanField())
            if school is not None
            else Value(False, output_field=BooleanField())
        )
        return units.annotate(own_school=flag).order_by("-own_school", "name")
    if school is None:
        return Unit.objects.none()
    return units.filter(pk=school.pk).annotate(own_school=Value(True, output_field=BooleanField()))


def _dean_office_scope(application, scope, scope_id, user):
    """Seçilmiş məktəb; seçilməyibsə müraciət edənin öz aidiyyəti. Aidiyyət yoxdursa seçim MƏCBURİDİR —
    əks halda müraciət heç bir dekanlığın növbəsinə düşmürdü (``requires_scope``)."""
    if not scope_id:
        if scope is None and school_choices(application, user).exists():
            raise TransitionDenied("scope.required", "Dekanlığı (məktəbi) seçin.")
        return scope
    try:
        selected = school_choices(application, user).filter(pk=scope_id).first()
    except (ValueError, TypeError, ValidationError):
        selected = None
    if selected is None:
        raise TransitionDenied("scope.required", "Dekanlığı (məktəbi) seçin.")
    return selected


def forward_scope(application, target_unit, scope_id=None, user=None):
    from .routing import resolve_scope_unit

    scope = resolve_scope_unit(target_unit, applicant_unit(application))
    if target_unit.code == DEAN_OFFICE_CODE:
        return _dean_office_scope(application, scope, scope_id, user)
    if target_unit.resolve_by != "chair":
        if scope_id:
            raise TransitionDenied("scope.invalid", "Bu şöbə üçün kafedra seçimi qəbul edilmir.")
        return scope
    if scope is not None and not scope_id:
        return scope
    try:
        selected = chair_choices(application, user).filter(pk=scope_id).first() if scope_id else None
    except (ValueError, TypeError, ValidationError):
        selected = None
    if selected is None:
        if _overseer(user, application):
            raise TransitionDenied("scope.required", "Kafedranı seçin.")
        raise TransitionDenied("scope.required", "Tələbənin məktəbinə aid kafedranı seçin.")
    return selected


def forward_scope_options(application, user) -> list[dict]:
    """Detal payload-ı üçün kafedra siyahısı; başqa məktəbin kafedrasında məktəb adı alt sətirdə."""
    units = list(chair_choices(application, user))
    if not units:
        return []
    schools = []
    if any(not unit.own_school for unit in units):
        Unit = django_apps.get_model("organizations", "OrgUnit")
        schools = list(
            Unit.objects.filter(organization_id=application.organization_id, unit_type=OrgUnitType.FACULTY).only(
                "path", "name"
            )
        )
        schools.sort(key=lambda school: -len(school.path))  # ən yaxın (dərin) məktəb əvvəl

    def school_name(unit):
        for school in schools:
            if unit.path.startswith(school.path + "/"):
                return school.name
        return ""

    return [
        {
            "id": str(unit.pk),
            "name": unit.name,
            "own_school": bool(unit.own_school),
            "school": "" if unit.own_school else school_name(unit),
        }
        for unit in units
    ]


def forward_school_options(application, user) -> list[dict]:
    """Detal payload-ı üçün dekanlıq (məktəb) siyahısı."""
    return [
        {"id": str(unit.pk), "name": unit.name, "own_school": bool(unit.own_school)}
        for unit in school_choices(application, user)
    ]


def creation_schools(organization, family, scope_unit, unit) -> list:
    """Yaratma formasında dekanlıq seçimi — yalnız aidiyyəti tapılmayan (tələbə olmayan) göndərən üçün."""
    if unit is None or unit.code != DEAN_OFFICE_CODE or scope_unit is not None or family == "student":
        return []
    Unit = django_apps.get_model("organizations", "OrgUnit")
    return list(
        Unit.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.FACULTY).order_by("name")
    )


def creation_scope(organization, family, scope_unit, unit, scope_id):
    """Yaratmada seçilmiş dekanlıq; seçim tələb olunub verilməyibsə — imtina (heç kimin növbəsinə düşməsin)."""
    schools = creation_schools(organization, family, scope_unit, unit)
    if not schools:
        return scope_unit
    selected = next((school for school in schools if str(school.pk) == str(scope_id or "").strip()), None)
    if selected is None:
        raise TransitionDenied("scope.required", "Dekanlığı (məktəbi) seçin.")
    return selected
