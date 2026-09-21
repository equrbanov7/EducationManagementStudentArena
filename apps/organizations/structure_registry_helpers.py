"""Fakültələr / Kafedralar reyestri əməlləri — ortaq köməkçilər.

``structure_registry_actions.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21):
JSON cavab qurucuları, görünən vahid / aktiv üzv / rol axtarışı, tələbə qoruması
və üzvlük yaratma-aktivləşdirmə. Əməl işləyiciləri ``structure_registry_unit_actions.py``,
«Heyət» çekmecəsi və namizəd axtarışı ``structure_registry_lookups.py``-dadır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.http import JsonResponse

from core.constants import OrgUnitType
from core.roles import ProfileRole

from .models import Membership, Role
from .structure_views.constants import KAFEDRA_UNIT_TYPES
from .views import _visible_units_queryset

_CTX = "organizations.registry"

#: Arxivləmə üçün minimum səbəb uzunluğu — ağac əməlləri ilə eyni (audit qaydası).
ARCHIVE_REASON_MIN = 20

REGISTRY_UNIT_TYPES = (OrgUnitType.FACULTY, *KAFEDRA_UNIT_TYPES)

#: Bir səhifədə neçə namizəd (axtarışlı seçicinin infinite-scroll addımı).
CANDIDATE_PAGE_SIZE = 20
CANDIDATE_MAX_PAGE_SIZE = 50


# ─── Cavab köməkçiləri ──────────────────────────────────────────────────────


def _error(message, *, status=400, code="invalid", field=None):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _ok(message="", **extra):
    payload = {"ok": True, "message": message}
    payload.update(extra)
    return JsonResponse(payload)


def _forbidden(message):
    return _error(message, status=403, code="forbidden")


def _visible_unit(organization, scope, unit_id, unit_types=REGISTRY_UNIT_TYPES):
    if not unit_id:
        return None
    return (
        _visible_units_queryset(organization, scope)
        .filter(pk=unit_id, unit_type__in=unit_types)
        .select_related("parent", "head")
        .first()
    )


def _display_name(user):
    return user.get_full_name() or user.username


def _is_student(organization, user) -> bool:
    """`apps.accounts.services.people.actions._assert_not_student` ilə EYNİ meyar."""
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=user, is_active=True).exists()
        or Membership.objects.filter(
            organization=organization,
            user=user,
            is_active=True,
            role__is_active=True,
            role__name__in=(ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT),
        ).exists()
    )


def _active_member_user(organization, user_id):
    """İstifadəçi YALNIZ bu təşkilatın aktiv üzvü ola bilər (cross-tenant qapısı)."""
    if not user_id:
        return None
    membership = (
        Membership.objects.filter(organization=organization, is_active=True, user__is_active=True, user_id=user_id)
        .select_related("user")
        .first()
    )
    return membership.user if membership else None


def _role(organization, name):
    return Role.objects.filter(organization=organization, name=name, is_active=True).first()


def _ensure_membership(organization, user, role, scope_unit, *, assigned_by):
    """(user, org, role, scope_unit) üzvlüyünü yarat və ya aktivləşdir.

    Qaytarır: ``(membership, created, reactivated)``. Artıq aktivdirsə
    ``(membership, False, False)``.
    """
    membership = Membership.objects.filter(
        organization=organization, user=user, role=role, scope_unit=scope_unit
    ).first()
    if membership is None:
        membership = Membership.objects.create(
            organization=organization,
            user=user,
            role=role,
            scope_unit=scope_unit,
            assigned_by=assigned_by,
            is_active=True,
        )
        return membership, True, False
    if not membership.is_active:
        membership.is_active = True
        membership.assigned_by = assigned_by
        membership.save(update_fields=["is_active", "assigned_by", "updated_at"])
        return membership, False, True
    return membership, False, False


def _in_subtree(unit, candidate) -> bool:
    return candidate.id == unit.id or candidate.path.startswith(f"{unit.path}/")
