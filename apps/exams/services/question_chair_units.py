"""Sual göndərişinin KAFEDRA bağı və kafedra-təsdiq əhatəsi.

Sahibin tələbi (2026-09): müəllimin imtahan sualları İmtahan Mərkəzinə
BİRBAŞA getmir — əvvəlcə KAFEDRA MÜDİRİ təsdiqləyir.  Bunun üçün hər
göndərişin hansı kafedraya aid olduğu həll olunmalıdır.

Həll sırası (sillabusun ``apps/syllabus/services/units.py`` məntiqi ilə EYNİ,
amma modul sərhədini keçməmək üçün burada təkrar qurulub):

1. Göndərişin QRUP(lar)ının ``org_unit``-indən yuxarı ilk ``chair`` /
   ``department`` tipli əcdad.  Ağac dərinliyi FƏRZ EDİLMİR.
2. Tapılmasa — MÜƏLLİMİN öz aktiv kafedra üzvlüyünün bölməsi.  Köçürülmüş
   tenant-da ixtisas birbaşa fakültəyə bağlıdır, ona görə (1) tez-tez boş
   qalır, müəllim isə kafedraya bağlıdır.
3. O da yoxdursa ``None`` — bu halda göndəriş DEKANLIĞA yönləndirilir
   (``routed_to_dean``); heç vaxt səssizcə mərkəzə DÜŞMÜR.

Əhatə (kim qərar verə bilər)
----------------------------
* ORGANIZATION scope-lu rol (RİM, rektor/prorektor `*`) — bütün təşkilat.
* KAFEDRA səviyyəli ``scope_unit`` — yalnız öz kafedrasının göndərişi.
* Daha yuxarı (fakültə) scope — YALNIZ göndəriş dekanlığa yönləndirilibsə
  (``routed_to_dean``); əks halda dekan qərar VERMİR (fail-closed).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from apps.organizations.unit_heads import (
    ancestor_unit_ids,
    chair_head_memberships_for_unit,
    dean_memberships_for_unit,
    resolve_ancestor,
)
from core.constants import OrgUnitType, RoleScopeType
from core.permissions import has_permission

#: Kafedra rolunu daşıyan bölmə tipləri (``department`` tarixi sinonimdir).
CHAIR_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)

#: Kafedra təsdiq növbəsinin kanonik icazə açarı.
QUESTION_CHAIR_REVIEW_PERMISSION = "question.chair_review"


def resolve_chair_unit(unit):
    """``unit``-dən yuxarı ən yaxın kafedra; tapılmasa ``None`` (fail-closed)."""
    if unit is None:
        return None
    for unit_type in CHAIR_UNIT_TYPES:
        found = resolve_ancestor(unit, unit_type)
        if found is not None:
            return found
    return None


def teacher_chair_unit(teacher, organization):
    """Müəllimin AKTİV kafedra üzvlüyünün bölməsi (struktur bağı olmayan hal)."""
    if teacher is None or organization is None:
        return None
    Membership = django_apps.get_model("organizations", "Membership")
    membership = (
        Membership.objects.filter(
            organization=organization,
            user=teacher,
            is_active=True,
            scope_unit__unit_type__in=CHAIR_UNIT_TYPES,
        )
        .select_related("scope_unit")
        .order_by("-is_primary", "pk")
        .first()
    )
    return membership.scope_unit if membership else None


def resolve_submission_chair_unit(*, organization, teacher, groups=()):
    """Göndərişin kafedrası: qrup əcdadı → müəllimin kafedrası → ``None``."""
    for group in groups or ():
        if group is None:
            continue
        chair = resolve_chair_unit(getattr(group, "org_unit", None))
        if chair is not None:
            return chair
    return teacher_chair_unit(teacher, organization)


# ---------------------------------------------------------------------------
# Marşrutlaşdırma hədəfləri
# ---------------------------------------------------------------------------
def chair_route_targets(organization, chair_unit):
    """(hədəf üzvlüklər, dekanlığa_yönləndirildi) cütü.

    Kafedra müdiri VARSA ona gedir.  Yoxdursa (və ya kafedra ümumiyyətlə həll
    olunmayıbsa) DEKANLIĞA — açıq qeyd ilə.  Heç biri yoxdursa boş siyahı
    qaytarılır; göndəriş yenə kafedra mərhələsində QALIR (mərkəzə düşmür) və
    UI «təsdiqləyici tapılmadı» xəbərdarlığını göstərir.
    """
    if chair_unit is not None:
        chair_memberships = list(chair_head_memberships_for_unit(organization, chair_unit))
        if chair_memberships:
            return chair_memberships, False
    dean_memberships = list(dean_memberships_for_unit(organization, chair_unit)) if chair_unit is not None else []
    return dean_memberships, True


# ---------------------------------------------------------------------------
# Əhatə (fail-closed)
# ---------------------------------------------------------------------------
def _chair_review_memberships(user, organization):
    Membership = django_apps.get_model("organizations", "Membership")
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return []
    memberships = Membership.objects.filter(
        organization=organization,
        user=user,
        is_active=True,
        role__is_active=True,
    ).select_related("role", "scope_unit")
    return [m for m in memberships if has_permission(list(m.role.permissions or []), QUESTION_CHAIR_REVIEW_PERMISSION)]


def is_privileged_reviewer(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def has_chair_review_access(user, organization) -> bool:
    """Aktor ÜMUMİYYƏTLƏ kafedra təsdiq növbəsini aça bilirmi (yalnız görünürlük)."""
    if is_privileged_reviewer(user):
        return True
    return bool(_chair_review_memberships(user, organization))


def can_review_submission_as_chair(user, submission) -> bool:
    """Aktor MƏHZ bu göndərişə kafedra qərarı verə bilirmi (fail-closed)."""
    if is_privileged_reviewer(user):
        return True
    organization = submission.organization
    covering_ids = set(ancestor_unit_ids(submission.chair_unit)) if submission.chair_unit_id else set()
    for membership in _chair_review_memberships(user, organization):
        if membership.role.scope_type == RoleScopeType.ORGANIZATION:
            return True
        scope_unit = membership.scope_unit
        if scope_unit is None or not covering_ids:
            continue
        if str(scope_unit.pk) not in covering_ids:
            continue
        if scope_unit.unit_type in CHAIR_UNIT_TYPES:
            return True
        # Fakültə/yuxarı scope — YALNIZ dekanlıq fallback-ında qərar verir.
        if submission.routed_to_dean:
            return True
    return False


def chair_queue_filter(user, organization):
    """Aktorun kafedra növbəsi üçün ``Q`` filtri; əhatə yoxdursa ``None``.

    ``None`` = «heç nə görünmür» (fail-closed) — çağıran tərəf boş queryset
    qaytarmalıdır.
    """
    if is_privileged_reviewer(user):
        return Q()
    memberships = _chair_review_memberships(user, organization)
    if not memberships:
        return None
    condition = Q()
    matched = False
    for membership in memberships:
        if membership.role.scope_type == RoleScopeType.ORGANIZATION:
            return Q()
        scope_unit = membership.scope_unit
        if scope_unit is None:
            continue
        prefix = (getattr(scope_unit, "path", "") or "").strip("/")
        if not prefix:
            continue
        subtree = Q(chair_unit__path__startswith=prefix)
        if scope_unit.unit_type not in CHAIR_UNIT_TYPES:
            # Dekanlıq YALNIZ fallback göndərişləri görür.
            subtree &= Q(routed_to_dean=True)
        condition |= subtree
        matched = True
    return condition if matched else None


__all__ = [
    "CHAIR_UNIT_TYPES",
    "QUESTION_CHAIR_REVIEW_PERMISSION",
    "can_review_submission_as_chair",
    "chair_queue_filter",
    "chair_route_targets",
    "has_chair_review_access",
    "is_privileged_reviewer",
    "resolve_chair_unit",
    "resolve_submission_chair_unit",
    "teacher_chair_unit",
]
