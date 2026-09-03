"""Bir şəxsin detal kartı — modal / ayrıca səhifə üçün.

Kart HEÇ BİR yeni səlahiyyət açmır: hədəf əvvəlcə aktorun GÖRÜNƏN kataloqunda
olmalıdır (:func:`actions.assert_in_catalog_scope`), sonra sahələr elə həmin
icazə açarları ilə süzülür (əlaqə → ``people.view_contacts``, demoqrafiya →
``people.view_demographics``).

Üzvlük siyahısı RİM kartından TƏKRAR YAZILMIR — ``rim.detail`` funksiyası
çağırılır (ikili rol dəstəyi orada həll olunub).
"""

from __future__ import annotations

from django.urls import reverse

from ..rim.detail import serialize_memberships
from .actions import assert_in_catalog_scope, load_target
from .constants import TEACHER_ROLE_NAMES
from .filters import STATUS_ACTIVE, STATUS_BLOCKED
from .rows import identity_row, resolve_unit_ancestors

MAX_DETAIL_ROWS = 60


def _teaching_rows(user, organization, *, limit=MAX_DETAIL_ROWS):
    from apps.registrar.models import CourseOffering

    offerings = (
        CourseOffering.objects.filter(organization=organization, instructor=user, is_active=True)
        .select_related("subject", "group", "period")
        .order_by("-period__academic_year", "period__name", "subject__name")[:limit]
    )
    return [
        {
            "subject": offering.subject.name if offering.subject_id else "",
            "subject_code": offering.subject.code if offering.subject_id else "",
            "group": offering.group.name if offering.group_id else "",
            "period": offering.period.name if offering.period_id else "",
            "academic_year": offering.period.academic_year if offering.period_id else "",
        }
        for offering in offerings
    ]


def _academic_rows(user, organization, *, limit=MAX_DETAIL_ROWS):
    from apps.registrar.models import StudentAcademicRecord

    records = (
        StudentAcademicRecord.objects.filter(organization=organization, student=user)
        .select_related("program", "group", "curriculum")
        .order_by("-admission_year")[:limit]
    )
    return [
        {
            # Ad ŞİFRSİZ + şifr ayrıca `program_code` nişanında (eyni naxış:
            # `academic.py`, `context_builder/_helpers.py`) — birləşmiş
            # `display_label` versək ilk istehlakçı şifri iki dəfə çap edərdi.
            "program": record.program.name if record.program_id else "",
            "program_code": record.program.official_code_pair if record.program_id else "",
            "group": record.group.name if record.group_id else "",
            "admission_year": record.admission_year,
            "status": record.status,
            "is_active": bool(record.is_active),
        }
        for record in records
    ]


def _is_teacher(user, organization) -> bool:
    from apps.organizations.models import Membership

    return Membership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        role__is_active=True,
        role__name__in=TEACHER_ROLE_NAMES,
    ).exists()


def build_detail(*, actor, user_id, request=None, today=None) -> dict:
    """Detal kartı. Scope-dan kənar hədəf üçün ``RimAccessError`` (404) atılır."""
    target = load_target(actor, user_id)
    catalog = assert_in_catalog_scope(actor, target, request=request)

    organization = actor.organization
    row = identity_row(target, actor=actor, today=today)
    row["kind"] = catalog
    row["profile_url"] = reverse("accounts:public_profile", kwargs={"username": target.username})
    row["last_login"] = target.last_login.isoformat() if target.last_login else ""
    row["date_joined"] = target.date_joined.isoformat() if target.date_joined else ""
    row["memberships"] = serialize_memberships(target, organization)

    is_teacher = _is_teacher(target, organization) if organization is not None else False
    row["is_teacher"] = is_teacher
    row["teaching"] = _teaching_rows(target, organization) if (organization and is_teacher) else []
    row["academic"] = _academic_rows(target, organization) if (organization and catalog == "student") else []

    unit_ids = [membership for membership in row["memberships"] if membership.get("scope_unit")]
    row["units"] = [membership["scope_unit"] for membership in unit_ids]

    status = row["status"]
    row["actions"] = {
        "block": actor.can_manage_status and status == STATUS_ACTIVE,
        "unblock": actor.can_manage_status and status == STATUS_BLOCKED,
        "grant_teacher": actor.can_manage_teacher_role and not is_teacher,
        "revoke_teacher": actor.can_manage_teacher_role and is_teacher,
    }
    return {"has_access": True, "person": row}


def structure_names_for(units, *, organization):
    """Köməkçi: unit siyahısı üçün fakültə/kafedra adları (detal başlığı üçün)."""
    return resolve_unit_ancestors(units, organization=organization)


__all__ = ["MAX_DETAIL_ROWS", "build_detail", "structure_names_for"]
