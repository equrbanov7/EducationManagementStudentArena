"""Registrar/organizations sorğuları — YALNIZ app registry ilə (``get_model``).

Modul sərhədi: bu app ``apps.registrar``-ı Python səviyyəsində İDXAL ETMİR
(``scripts/context_map.py`` ratchet-i + registrar-ın bu app-ı heç vaxt idxal
etməməsi şərti). Jurnal müəllimi yoxlaması registrar-ın
``journal_access.is_direct_editor`` + ``integrity.is_authorized_instructor``
qaydasının GÜZGÜSÜDÜR: canlı müəllim (açılışın və ya dərsin ``instructor``-u,
aktiv üzvlük + ``grade.input``), org sahibi, superuser, İKT/RİM rəhbəri.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.permissions import has_permission, is_superadmin_user

from ..constants import INSTRUCTOR_PERMISSION

#: ``registrar.Enrollment.Status.ENROLLED`` — auditoriyanın yeganə statusu.
ENROLLED = "enrolled"


def offering_model():
    return django_apps.get_model("registrar", "CourseOffering")


def enrollment_model():
    return django_apps.get_model("registrar", "Enrollment")


def lesson_model():
    return django_apps.get_model("registrar", "Lesson")


def subject_model():
    return django_apps.get_model("registrar", "Subject")


def membership_model():
    return django_apps.get_model("organizations", "Membership")


def org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def _pk(value):
    return getattr(value, "pk", value)


def is_authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def is_org_admin(user, organization) -> bool:
    """Superuser / superadmin / təşkilat sahibi / İKT (RİM) rəhbəri — hər şeyə baxır və idarə edir."""
    if not is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False) or is_superadmin_user(user):
        return True
    if getattr(user, "is_ikt_rehber", False):
        return True
    owner_id = getattr(organization, "owner_id", None)
    return owner_id is not None and owner_id == user.pk


def has_instructor_authority(user, organization) -> bool:
    """Aktiv, eyni-təşkilatlı üzvlüyün rolu ``grade.input`` verirmi (registrar ``integrity`` güzgüsü)."""
    if not is_authenticated(user) or organization is None:
        return False
    memberships = (
        membership_model()
        .objects.filter(
            organization_id=_pk(organization),
            organization__is_active=True,
            user_id=user.pk,
            user__is_active=True,
            is_active=True,
            role__is_active=True,
            role__organization_id=_pk(organization),
        )
        .select_related("role")
    )
    return any(
        has_permission(list(membership.role.permissions or []), INSTRUCTOR_PERMISSION) for membership in memberships
    )


def lesson_instructor_offering_ids(user):
    """Aktorun DƏRS səviyyəsində (``Lesson.instructor``) keçdiyi açılışların id subquery-si."""
    return lesson_model().objects.filter(instructor_id=_pk(user)).values("offering_id")


def taught_offerings_q(user, *, prefix: str = "") -> Q:
    """``CourseOffering`` (və ya ``<prefix>`` ilə əlaqəli) Q — aktorun müəllimi olduğu açılışlar."""
    return Q(**{f"{prefix}instructor_id": _pk(user)}) | Q(**{f"{prefix}pk__in": lesson_instructor_offering_ids(user)})


def teaches_offering(user, offering) -> bool:
    """Aktor bu açılışın CANLI müəllimidirmi (və ya inzibatçıdır).

    Açılışın ``instructor``-u VƏ YA açılışda dərs keçən ``Lesson.instructor``
    (fənn iki müəllim arasında bölünəndə) — hər iki halda aktiv ``grade.input``
    üzvlüyü tələb olunur; təhvil verilmiş köhnə müəllim avtomatik düşür.
    """
    if not is_authenticated(user) or offering is None:
        return False
    organization = offering.organization
    if is_org_admin(user, organization):
        return True
    is_named = offering.instructor_id == user.pk
    if not is_named:
        is_named = lesson_model().objects.filter(offering_id=offering.pk, instructor_id=user.pk).exists()
    return is_named and has_instructor_authority(user, organization)


def teaches_subject(user, *, organization, subject, period=None) -> bool:
    """Aktorun bu fənndən (semestr verilibsə həmin semestrdə) ən azı bir açılışı varmı."""
    if not is_authenticated(user):
        return False
    offerings = offering_model().objects.filter(organization=organization, subject=subject)
    if period is not None:
        offerings = offerings.filter(period=period)
    return offerings.filter(taught_offerings_q(user)).exists() and has_instructor_authority(user, organization)


def active_enrollment(offering_id, student) -> object | None:
    """Tələbənin açılışdakı AKTİV (``enrolled``) qeydiyyatı və ya ``None``."""
    if not is_authenticated(student):
        return None
    return (
        enrollment_model()
        .objects.filter(offering_id=_pk(offering_id), student_id=student.pk, status=ENROLLED)
        .select_related("offering", "offering__organization")
        .first()
    )


def audience_enrollments(offering_ids):
    """Təyinat auditoriyası: açılış(lar)ın ``enrolled`` qeydiyyatları (guest daxil, köçürülmüş xaric)."""
    ids = [_pk(value) for value in offering_ids] if isinstance(offering_ids, (list, tuple, set)) else offering_ids
    return enrollment_model().objects.filter(offering_id__in=ids, status=ENROLLED)


def group_in_scope(scope, organization, group_id) -> bool:
    """``UnitScope`` qrupu (OrgUnit) örtürmü — fail-closed."""
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    if group_id is None:
        return False
    return (
        org_unit_model().objects.filter(organization=organization, pk=group_id).filter(scope.unit_subtree_q()).exists()
    )


def scope_group_ids_q(scope, organization, *, field: str) -> Q:
    """Toplu filtr: ``field`` (qrup FK yolu) aktorun UNIT əhatəsindəki qruplardan biridir.

    Org-wide əhatəni çağıran ayrıca həll edir (boş ``Q()`` OR-da düşür).
    """
    units = org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q()).values("pk")
    return Q(**{f"{field}__in": units})


__all__ = [
    "ENROLLED",
    "active_enrollment",
    "audience_enrollments",
    "enrollment_model",
    "group_in_scope",
    "has_instructor_authority",
    "is_authenticated",
    "is_org_admin",
    "lesson_instructor_offering_ids",
    "lesson_model",
    "membership_model",
    "offering_model",
    "org_unit_model",
    "scope_group_ids_q",
    "subject_model",
    "taught_offerings_q",
    "teaches_offering",
    "teaches_subject",
]
