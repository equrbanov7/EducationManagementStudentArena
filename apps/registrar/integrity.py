"""Tenant-integrity validators for registrar domain writes.

PostgreSQL migration guards are the authoritative protection for raw SQL and
bulk import paths.  These helpers mirror the same rules in Python so services,
forms and import adapters can fail before reaching the database.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError

from core.permissions import has_permission

INSTRUCTOR_PERMISSION = "grade.input"


def _pk(value):
    return getattr(value, "pk", value)


def _organization_id(value):
    return getattr(value, "organization_id", None)


def validate_same_organization(*, organization, **relations) -> None:
    """Require every non-null organization-scoped relation to share the tenant."""
    organization_id = _pk(organization)
    errors = {}
    for field_name, relation in relations.items():
        if relation is None:
            continue
        if _organization_id(relation) != organization_id:
            errors[field_name] = "Bağlı obyekt eyni təşkilata aid olmalıdır."
    if errors:
        raise ValidationError(errors)


def _active_membership_roles(*, organization, user):
    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(
        organization_id=_pk(organization),
        organization__is_active=True,
        user_id=_pk(user),
        user__is_active=True,
        is_active=True,
        role__is_active=True,
        role__organization_id=_pk(organization),
    ).select_related("role")


def eligible_instructor_user_ids(*, organization) -> set:
    """Return active member IDs whose active role grants grade input."""
    Membership = django_apps.get_model("organizations", "Membership")
    memberships = Membership.objects.filter(
        organization_id=_pk(organization),
        organization__is_active=True,
        user__is_active=True,
        is_active=True,
        role__is_active=True,
        role__organization_id=_pk(organization),
    ).select_related("role")
    return {
        membership.user_id
        for membership in memberships
        if has_permission(list(membership.role.permissions or []), INSTRUCTOR_PERMISSION)
    }


def validate_active_member(*, organization, user, field_name="student") -> None:
    """Require an active membership backed by an active same-tenant role."""
    if user is None or not _active_membership_roles(organization=organization, user=user).exists():
        raise ValidationError({field_name: "İstifadəçinin bu təşkilatda aktiv üzvlüyü olmalıdır."})


def validate_same_organization_actor(*, organization, user, field_name="actor", require_active=False) -> None:
    """Require an audit actor to have a durable relationship to the tenant.

    Historical actor references intentionally accept inactive memberships: a
    later revocation must not invalidate an earlier grade/correction decision.
    Organization owners and Django superusers are valid without a membership,
    matching the platform's controlled administrative paths.
    """
    if user is None:
        return
    organization_id = _pk(organization)
    is_superuser = getattr(user, "is_superuser", False)
    owner_id = getattr(organization, "owner_id", None)
    if require_active:
        Organization = django_apps.get_model("organizations", "Organization")
        active_organization = Organization.objects.filter(pk=organization_id, is_active=True).values("owner_id").first()
        active_user = (
            user._meta.model._default_manager.filter(pk=_pk(user), is_active=True).values("is_superuser").first()
        )
        if active_organization is None or active_user is None:
            raise ValidationError({field_name: "İcraçı və təşkilat aktiv olmalıdır."})
        owner_id = active_organization["owner_id"]
        is_superuser = active_user["is_superuser"]
    if is_superuser or owner_id == _pk(user):
        return
    Membership = django_apps.get_model("organizations", "Membership")
    memberships = Membership.objects.filter(organization_id=organization_id, user_id=_pk(user))
    if require_active:
        if not getattr(user, "is_active", False):
            raise ValidationError({field_name: "İcraçı aktiv istifadəçi olmalıdır."})
        memberships = memberships.filter(
            organization__is_active=True,
            user__is_active=True,
            is_active=True,
            role__is_active=True,
            role__organization_id=organization_id,
        )
    if memberships.exists():
        return
    raise ValidationError({field_name: "İcraçı bu təşkilatla əlaqəli üzv olmalıdır."})


def is_authorized_instructor(*, organization, instructor) -> bool:
    """Return whether the assigned user still has live grade-input authority."""
    if instructor is None:
        return False
    roles = _active_membership_roles(organization=organization, user=instructor)
    return any(has_permission(list(membership.role.permissions or []), INSTRUCTOR_PERMISSION) for membership in roles)


def validate_instructor_assignment(*, organization, instructor, field_name="instructor") -> None:
    """Require an active same-tenant membership that grants ``grade.input``.

    Permission evaluation intentionally uses the central wildcard/legacy-alias
    matcher instead of role-name checks, so custom roles remain supported.
    """
    if instructor is None:
        return
    if is_authorized_instructor(organization=organization, instructor=instructor):
        return
    raise ValidationError(
        {field_name: "Müəllimin bu təşkilatda aktiv və qiymət-daxiletmə səlahiyyətli üzvlüyü olmalıdır."}
    )


def validate_student_record_target(*, organization, student, program, curriculum, group=None) -> None:
    """Validate the core parent and member links of a student academic record."""
    validate_same_organization(
        organization=organization,
        program=program,
        curriculum=curriculum,
        group=group,
    )
    if curriculum is not None and program is not None and curriculum.program_id != _pk(program):
        raise ValidationError({"curriculum": "Seçilən tədris planı bu ixtisasa aid deyil."})
    validate_active_member(organization=organization, user=student, field_name="student")


def validate_offering_target(*, organization, subject, period, group=None, course=None, instructor=None) -> None:
    """Validate the tenant parents and optional instructor of an offering."""
    validate_same_organization(
        organization=organization,
        subject=subject,
        period=period,
        group=group,
        course=course,
    )
    validate_instructor_assignment(organization=organization, instructor=instructor)


def validate_enrollment_target(*, organization, student, offering) -> None:
    """Validate enrollment tenant ownership and the student's membership."""
    validate_same_organization(organization=organization, offering=offering)
    validate_active_member(organization=organization, user=student, field_name="student")


def validate_lesson_instructor(*, offering, instructor) -> None:
    """Validate an explicit lesson-level instructor assignment."""
    if instructor is not None:
        validate_instructor_assignment(
            organization=offering.organization,
            instructor=instructor,
            field_name="instructor",
        )


def validate_group_elective_target(
    *, organization, group, curriculum, period, elective_group, subject, decided_by=None
) -> None:
    """Validate the tenant, block option and durable decision attribution."""
    validate_same_organization(
        organization=organization,
        group=group,
        curriculum=curriculum,
        period=period,
        subject=subject,
    )
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    if not CurriculumSubject.objects.filter(
        curriculum_id=_pk(curriculum),
        subject_id=_pk(subject),
        elective_group=elective_group,
        is_elective=True,
    ).exists():
        raise ValidationError({"chosen_subject": "Seçilən fənn bu tədris planının seçmə blokuna aid deyil."})
    validate_same_organization_actor(
        organization=organization,
        user=decided_by,
        field_name="decided_by",
        require_active=True,
    )
