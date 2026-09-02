"""Marşrutlaşdırma — «bu müraciət kimə gedir» sualının YEGANƏ cavabı.

Dizayn §3.2: göndərən şöbəni SEÇMİR. Ünvan SERVER tərəfdə hesablanır:

    növ (+ göndərənin ailəsi)  →  şöbə kodu  →  ApplicationUnit
    göndərənin öz bölməsi      →  şöbənin resolve_by tipli ƏCDADI  →  scope_unit

Klientdən gələn heç bir şöbə/rol dəyəri istifadə olunmur.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from apps.organizations.unit_heads import resolve_ancestor
from core.constants import RoleScopeType

from ..constants import RESOLVE_BY_FALLBACK_UNIT_TYPES, ResolveBy, SenderFamily
from ..models import ApplicationUnit

#: Müəllim/assistent sayılan üzvlük rol adları.
_TEACHER_ROLE_NAMES = frozenset(
    {"teacher", "instructor", "professor", "associate_professor", "assistant", "assistant_teacher", "lab_assistant"}
)
_STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})


def _active_memberships(user, organization):
    from apps.organizations.models import Membership

    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return []
    return list(
        Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
        ).select_related("role", "scope_unit")
    )


def sender_family_for(user, organization) -> str | None:
    """İstifadəçinin göndərən ailəsi: ``student`` / ``teacher`` / ``staff``.

    AKTİV üzvlüyü olmayan istifadəçi müraciət YARADA BİLMİR → ``None``.
    Üzvlükdən oxunur (``user.is_student`` propertisi aktiv-təşkilat kontekstinə
    bağlıdır və servis qatında həmişə qurulmuş olmur).
    """
    memberships = _active_memberships(user, organization)
    if not memberships:
        return None
    role_names = {membership.role.name for membership in memberships}
    if role_names & _STUDENT_ROLE_NAMES:
        return SenderFamily.STUDENT.value
    if role_names & _TEACHER_ROLE_NAMES:
        return SenderFamily.TEACHER.value
    return SenderFamily.STAFF.value


def sender_scope_unit_for(user, organization, family: str):
    """Göndərənin ÖZ bölməsi — tələbə üçün qrup, digərləri üçün üzvlük scope-u.

    MODUL SƏRHƏDİ: ``registrar`` modeli app registry ilə həll olunur ki,
    ``applications → registrar`` statik idxal kənarı yaranmasın.
    """
    if family == SenderFamily.STUDENT.value:
        StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
        record = (
            StudentAcademicRecord.objects.filter(
                organization=organization,
                student=user,
                is_active=True,
                group__isnull=False,
            )
            .select_related("group")
            .order_by("-created_at")
            .first()
        )
        if record is not None and record.group_id:
            return record.group

    for membership in _active_memberships(user, organization):
        if membership.role.scope_type == RoleScopeType.UNIT and membership.scope_unit_id:
            return membership.scope_unit
    return None


def resolve_scope_unit(unit: ApplicationUnit, sender_unit):
    """Şöbənin aidiyyət bölməsi — göndərənin ``resolve_by`` tipli əcdadı.

    ``resolve_by == organization`` → ``None`` (mərkəzi şöbə, bütün təşkilat).
    Əcdad tapılmazsa da ``None`` qaytarılır: müraciət İTMİR, sadəcə həmin rolun
    BÜTÜN daşıyıcılarına açıq olur (fail-open GÖRÜNÜŞ, fail-closed ƏMƏL deyil —
    əməl yenə yalnız cari şöbənin rolunu daşıyanlara açıqdır).
    """
    if unit.resolve_by == ResolveBy.ORGANIZATION.value:
        return None
    for unit_type in RESOLVE_BY_FALLBACK_UNIT_TYPES.get(unit.resolve_by, ()):
        ancestor = resolve_ancestor(sender_unit, unit_type)
        if ancestor is not None:
            return ancestor
    return None


def unit_by_code(organization, code: str):
    return ApplicationUnit.objects.filter(organization=organization, code=code, is_active=True).first()


def route_for(kind, user, *, organization=None, family=None, sender_unit=None):
    """``(unit, scope_unit, family, sender_unit)`` — müraciətin ünvanı.

    Növün ``route_overrides``-i ailəyə görə şöbəni dəyişir (məs. «Digər»).
    Override-dəki kod tapılmazsa ``target_unit``-ə düşülür.
    """
    organization = organization or kind.organization
    family = family or sender_family_for(user, organization)
    if family is None:
        return None, None, None, None
    if sender_unit is None:
        sender_unit = sender_scope_unit_for(user, organization, family)

    unit = unit_by_code(organization, kind.unit_code_for(family))
    if unit is None:
        unit = kind.target_unit
    return unit, resolve_scope_unit(unit, sender_unit), family, sender_unit


def allowed_kinds_for(organization, family: str):
    """Bu ailənin yarada biləcəyi AKTİV növlər (növbənin özü filtrləyir)."""
    from ..models import ApplicationKind

    if not family:
        return ApplicationKind.objects.none()
    queryset = ApplicationKind.objects.filter(organization=organization, is_active=True).select_related("target_unit")
    matching = [kind.pk for kind in queryset if kind.allows(family)]
    return ApplicationKind.objects.filter(pk__in=matching).select_related("target_unit").order_by("order", "label")


__all__ = [
    "allowed_kinds_for",
    "resolve_scope_unit",
    "route_for",
    "sender_family_for",
    "sender_scope_unit_for",
    "unit_by_code",
]
