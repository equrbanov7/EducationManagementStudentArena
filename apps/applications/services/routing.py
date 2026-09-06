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
from . import access

#: Müəllim/assistent sayılan üzvlük rol adları.
_TEACHER_ROLE_NAMES = frozenset(
    {"teacher", "instructor", "professor", "associate_professor", "assistant", "assistant_teacher", "lab_assistant"}
)
_STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})

#: ``route_for``-da «sender_unit verilməyib» ilə «sender_unit HƏLL OLUNUB, nəticə
#: None-dur» (məs. mərkəzi/org-scope aktor) fərqini ayırmaq üçün. ``None`` hər
#: ikisi üçün işlədilsəydi, ikincisi hər KIND üçün YENİDƏN hesablanardı — bu da
#: hər dövrədə eyni üzvlük+SAR sorğularını təkrarlayan gizli N+1 idi (QA
#: P2-26/P2-6: bölmə açılışında 80+ sorğu, 37-42 dublikat).
_UNRESOLVED = object()


def _active_memberships(user, organization):
    """``access.active_memberships``-in keşlənmiş nəticəsini istifadə edir.

    Əvvəllər bu modul EYNİ sorğunu ÖZ-ÖZÜNƏ, keşsiz təkrarlayırdı —
    ``access.active_memberships`` isə artıq ``organization``/``user`` üzrə
    request-daxili keşə malikdir. İki ayrı tətbiqin sinxron qalması riski
    yaratmamaq üçün bura sadəcə DELEGASİYA edir.
    """
    return access.active_memberships(user, organization)


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
    """Koda görə vahid axtarışı — ``access.active_units`` keşindən (0 əlavə sorğu).

    Əvvəllər hər çağırış ayrı ``SELECT ... WHERE code=…`` idi; ``route_for``
    hər KIND üçün (bir ailədə 3-19 arası) bunu çağırdığından bölmə açılışında
    onlarla əlavə sorğu yaranırdı. Kataloq artıq təşkilat üzrə keşlənib —
    burda sadəcə yaddaşdaxili axtarışdır.
    """
    for unit in access.active_units(organization):
        if unit.code == code:
            return unit
    return None


def route_for(kind, user, *, organization=None, family=None, sender_unit=_UNRESOLVED):
    """``(unit, scope_unit, family, sender_unit)`` — müraciətin ünvanı.

    Növün ``route_overrides``-i ailəyə görə şöbəni dəyişir (məs. «Digər»).
    Override-dəki kod tapılmazsa ``target_unit``-ə düşülür.

    ``sender_unit`` DEFAULT-u ``_UNRESOLVED``-dur, ``None`` DEYİL: çağıran
    (məs. bir dövrədə 19 KIND üçün) artıq HƏLL EDİLMİŞ ``sender_unit``-i
    ötürəndə onun nəticəsi HƏQİQƏTƏN ``None`` ola bilər (mərkəzi/org-scope
    aktor — heç bir şöbəyə bağlı deyil). ``None``-u «hələ hesablanmayıb» ilə
    qarışdırmaq hər KIND üçün ``sender_scope_unit_for``-u (deməli üzvlük və
    tələbənin akademik qeydi sorğularını) TƏKRAR işə salırdı.
    """
    organization = organization or kind.organization
    family = family or sender_family_for(user, organization)
    if family is None:
        return None, None, None, None
    if sender_unit is _UNRESOLVED:
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
