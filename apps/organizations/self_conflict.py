"""Tələbə + heyət rolu — «özünə və öz qrupuna toxunma» qapısı (sahib qaydası 2026-11-08).

Sahib: «Əgər istifadəçi təhsil alan tələbədirsə və 2-ci (işçi) rolu varsa — o rol ilə özü ilə, öz qrupu
ilə bağlı heç nə görə və edə bilməsin; sistem bloklasın. Bu hər rola aid olacaq.» Konkret hal: magistrant
(632/6 İ) öz dekanlığına (qrupu da orada) «tyutor» rolu alır.

Qayda MƏRKƏZİDİR — hər view-u ayrıca yamaq əvəzinə:

* **Görünüş** — :func:`apps.organizations.scoping.get_permission_scope` qarışıq (tələbə + heyət) istifadəçinin
  struktur əhatəsinə ``excluded_unit_ids`` (öz qrupu + alt/ana qrupları) qoyur; ``UnitScope.unit_subtree_q``,
  ``unit_in_scope``, ``scope_org_units``, ``user_scope_covers_unit`` onları çıxarır. Tələbə rolunun ÖZ daşıdığı
  açarlar (``course.view``, ``exam.view`` …) istisnadır — tələbə özünü-xidmət səthləri olduğu kimi qalır.
* **Yazı** — :func:`is_self_conflict` / :func:`deny_self_conflict` hədəf (özü, qrup yoldaşı, öz qrupu, öz
  jurnalı) ilə toqquşmanı yoxlayır; çağıran 403 qaytarır, rədd audit olunur.

QİYMƏT: tələbə OLMAYAN (və ya yalnız tələbə olan) istifadəçi üçün 0 əlavə sorğu — qərar ``get_permission_scope``-un
onsuz da yüklədiyi (middleware snapshot-undan gələn) üzvlük sətirlərindən verilir. Yalnız qarışıq istifadəçi üçün
registrar-ın qeydiyyat etdiyi resolver bir neçə sorğu ilə «öz əhatə»ni hesablayır; nəticə ``user`` instansında
(request ömrü) yaddaşa alınır və ``invalidate_permission_scope_cache`` ilə silinir.

MODUL SƏRHƏDİ: akademik qeyd/açılış registrar-dadır, organizations isə registrar-ı import edə bilməz (dövr) —
resolver ``RegistrarConfig.ready()``-də :func:`register_own_scope_resolver` ilə qoşulur (``student_transfer``
nümunəsi). Resolver qoşulmayıbsa qapı heç nəyi gizlətmir (bu yalnız registrar-sız test konfiqurasiyasında olur).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

#: Tələbə rolları və «heyət sayılmayan» rollar (``accounts.profile_completion.role_family`` ilə eyni tərif).
STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})
NON_STAFF_ROLE_NAMES = STUDENT_ROLE_NAMES | frozenset({"alumni", "parent", "member"})

_CACHE_ATTR = "_self_conflict_scope_cache"
_CTX = "organizations.self_conflict"
REASON_CODE = "self_conflict"


@dataclass(frozen=True)
class OwnScope:
    """Qarışıq istifadəçinin heyət rolu ilə toxuna BİLMƏDİYİ obyektlər (id-lər ``str`` kimi).

    * ``user_ids``     — özü;
    * ``student_ids``  — özü + qrup ailəsindəki tələbələr (``User`` pk — ``Enrollment.student`` mənasında);
    * ``record_ids``   — həmin tələbələrin ``StudentAcademicRecord`` pk-ları;
    * ``group_ids``    — öz qrupu + alt qrupları + ana qrupu (``subgroup_rollup.group_family``);
    * ``offering_ids`` — öz qrup ailəsinin açılışları + özünün yazıldığı açılışlar.
    """

    user_ids: frozenset = field(default_factory=frozenset)
    student_ids: frozenset = field(default_factory=frozenset)
    record_ids: frozenset = field(default_factory=frozenset)
    group_ids: frozenset = field(default_factory=frozenset)
    offering_ids: frozenset = field(default_factory=frozenset)

    def __bool__(self) -> bool:
        return bool(self.user_ids)


EMPTY_OWN_SCOPE = OwnScope()

_resolver = None


def register_own_scope_resolver(resolver) -> None:
    """Registrar ``ready()``-də: ``resolver(user, organization) -> OwnScope``."""
    if not callable(resolver):
        raise TypeError("Own-scope resolver must be callable")
    global _resolver
    _resolver = resolver


def _key(value) -> str:
    """Müqayisə açarı — UUID-in böyük/kiçik hərf və boşluq variantları eyni sayılır."""
    return str(value).strip().lower()


def _ids(values) -> frozenset:
    return frozenset(_key(value) for value in values if value is not None)


def build_own_scope(*, user_id, student_ids=(), record_ids=(), group_ids=(), offering_ids=()) -> OwnScope:
    """Resolver üçün normallaşdırılmış konstruktor (bütün id-lər ``str``)."""
    return OwnScope(
        user_ids=_ids([user_id]),
        student_ids=_ids([user_id, *student_ids]),
        record_ids=_ids(record_ids),
        group_ids=_ids(group_ids),
        offering_ids=_ids(offering_ids),
    )


def _role_name(membership) -> str:
    role = getattr(membership, "role", None)
    if role is None or not getattr(role, "is_active", True):
        return ""
    return str(getattr(role, "name", "") or "").strip().lower()


def is_student_membership(membership) -> bool:
    return _role_name(membership) in STUDENT_ROLE_NAMES


def is_mixed_student_staff(memberships) -> bool:
    """Aktiv üzvlüklər arasında HƏM tələbə, HƏM heyət rolu varmı (sorğusuz)."""
    names = {name for name in (_role_name(m) for m in memberships or ()) if name}
    return bool(names & STUDENT_ROLE_NAMES) and bool(names - NON_STAFF_ROLE_NAMES)


def _exempt(user, organization) -> bool:
    return (
        user is None
        or organization is None
        or not getattr(user, "is_authenticated", False)
        or getattr(user, "pk", None) is None  # model olmayan aktor (məs. sistem / test dublyoru)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_superadmin", False)
    )


def _known_memberships(user, organization):
    """Sorğusuz əldə olunan üzvlük sətirləri (yaddaş və ya middleware snapshot-u); yoxdursa ``None``."""
    cache = getattr(user, "_org_scope_memberships_cache", None)
    org_pk = getattr(organization, "pk", None)
    if cache is not None and org_pk in cache:
        return cache[org_pk]
    from .request_memberships import request_active_memberships

    rows = request_active_memberships(user, organization)
    return None if rows is None else [m for m in rows if m.role.is_active]


def own_scope(user, organization, *, memberships=None, cached_only=False) -> OwnScope:
    """Qarışıq (tələbə + heyət) istifadəçinin «öz əhatəsi»; digər hər kəs üçün boş (0 sorğu).

    ``memberships`` verilməzsə ``get_permission_scope``-un memoizasiya etdiyi üzvlük sətirləri işlənir
    (middleware snapshot-u varsa sorğusuz). Nəticə ``user`` instansında org üzrə saxlanılır.
    """
    if _exempt(user, organization):
        return EMPTY_OWN_SCOPE
    org_pk = getattr(organization, "pk", None)
    cache = getattr(user, _CACHE_ATTR, None)
    if cache is not None and org_pk in cache:
        return cache[org_pk]
    if memberships is None and cached_only:
        # Servis qatı (məs. ``save_marks``): HTTP qapısı üzvlükləri onsuz da yükləyib; birbaşa (request-siz)
        # çağırışda əlavə sorğu verilmir — orada son müdafiə DB trigger-idir (``registrar`` 0119).
        memberships = _known_memberships(user, organization)
        if memberships is None:
            return EMPTY_OWN_SCOPE
    if memberships is None:
        from .scoping import _permission_scope_memberships

        memberships = _permission_scope_memberships(user, organization)
    scope = EMPTY_OWN_SCOPE
    if is_mixed_student_staff(memberships) and _resolver is not None:
        scope = _resolver(user, organization) or EMPTY_OWN_SCOPE
    if cache is None:
        cache = {}
        try:
            setattr(user, _CACHE_ATTR, cache)
        except Exception:  # noqa: BLE001 — dəyişməz user obyektləri (nadir)
            return scope
    cache[org_pk] = scope
    return scope


def drop_own_scope_cache(user) -> None:
    """``invalidate_permission_scope_cache`` çağırır — üzvlük/qeyd dəyişəndə köhnə «öz əhatə» qalmasın."""
    try:
        if user is not None and hasattr(user, _CACHE_ATTR):
            delattr(user, _CACHE_ATTR)
    except Exception:  # noqa: BLE001
        pass


def self_conflict_targets(
    scope: OwnScope, *, user_id=None, student_id=None, record_id=None, group_id=None, offering_id=None
):
    """Toqquşan hədəf növləri (boş siyahı — toqquşma yoxdur)."""
    if not scope:
        return []
    hits = []
    if user_id is not None and _key(user_id) in scope.user_ids:
        hits.append("self")
    if student_id is not None and _key(student_id) in scope.student_ids:
        hits.append("student")
    if record_id is not None and _key(record_id) in scope.record_ids:
        hits.append("record")
    if group_id is not None and _key(group_id) in scope.group_ids:
        hits.append("group")
    if offering_id is not None and _key(offering_id) in scope.offering_ids:
        hits.append("offering")
    return hits


def is_self_conflict(user, organization, *, cached_only=False, **targets) -> bool:
    """Hədəf (``user_id`` / ``student_id`` / ``record_id`` / ``group_id`` / ``offering_id``) istifadəçinin
    özü, qrup yoldaşı, öz qrupu və ya öz jurnalıdırmı — yalnız qarışıq istifadəçi üçün ``True`` ola bilər."""
    return bool(self_conflict_targets(own_scope(user, organization, cached_only=cached_only), **targets))


def offering_self_conflict(user, offering) -> bool:
    """Açılış (jurnal) toqquşması: öz açılışı və ya öz qrup ailəsinin açılışı."""
    if offering is None:
        return False
    organization = getattr(offering, "organization", None)
    scope = own_scope(user, organization)
    if not scope:
        return False
    return bool(self_conflict_targets(scope, offering_id=offering.pk, group_id=getattr(offering, "group_id", None)))


def self_conflict_message() -> str:
    return pgettext(
        _CTX,
        "Siz bu təşkilatda həm də tələbəsiniz: işçi rolu ilə özünüzə, öz qrupunuza və öz jurnallarınıza "
        "aid əməliyyat apara bilməzsiniz.",
    )


def audit_self_conflict(user, organization, *, action: str, request=None, **targets) -> None:
    """Rəddi audit jurnalına yaz (``AuditAction.DENY``). Audit xətası rəddi heç vaxt ləğv etmir."""
    from core.audit import log_action
    from core.constants import AuditAction

    hits = self_conflict_targets(own_scope(user, organization), **targets)
    try:
        log_action(
            AuditAction.DENY,
            user=user,
            organization=organization,
            request=request,
            resource_type="organizations.self_conflict",
            resource_id=str(next((v for v in targets.values() if v is not None), ""))[:64],
            resource_repr=action[:200],
            new_values={"action": action, "targets": {k: str(v) for k, v in targets.items() if v is not None}},
            reason=f"{REASON_CODE}:{','.join(hits)}",
        )
    except Exception:  # noqa: BLE001 — audit yazısı uğursuz olsa da əməl rədd olunur
        import logging

        logging.getLogger(__name__).exception("self-conflict audit write failed")


def deny_self_conflict(user, organization, *, action: str, request=None, cached_only=False, **targets) -> str | None:
    """Toqquşma varsa audit yazıb istifadəçi mesajını qaytarır, yoxdursa ``None`` (0 sorğu — qeyri-qarışıq)."""
    if not is_self_conflict(user, organization, cached_only=cached_only, **targets):
        return None
    audit_self_conflict(user, organization, action=action, request=request, **targets)
    return self_conflict_message()


class SelfConflictDenied(PermissionDenied):
    """403 — ``core.views.handler403`` ``public_message``-i göstərir (JSON sorğuda JSON qaytarır)."""

    reason_code = REASON_CODE

    def __init__(self, message: str):
        super().__init__(message)
        self.public_message = message


def guard_self_conflict(user, organization, *, action: str, request=None, cached_only=False, **targets) -> None:
    """Toqquşma varsa audit yazıb :class:`SelfConflictDenied` qaldırır (qeyri-qarışıq istifadəçidə sorğusuz)."""
    message = deny_self_conflict(user, organization, action=action, request=request, cached_only=cached_only, **targets)
    if message:
        raise SelfConflictDenied(message)


def own_scope_excludes(user, organization, permission: str, memberships) -> frozenset:
    """``get_permission_scope`` üçün: bu açarın əhatəsindən çıxarılacaq qrup id-ləri.

    Açarı TƏLƏBƏ üzvlüyü də daşıyırsa (``course.view`` …) heç nə çıxarılmır — tələbənin öz səthi qırılmasın.
    """
    if not is_mixed_student_staff(memberships):
        return frozenset()
    from core.permissions import has_permission

    if any(
        is_student_membership(m) and has_permission(list(m.role.permissions or []), permission) for m in memberships
    ):
        return frozenset()
    return own_scope(user, organization, memberships=memberships).group_ids


__all__ = [
    "EMPTY_OWN_SCOPE",
    "NON_STAFF_ROLE_NAMES",
    "OwnScope",
    "REASON_CODE",
    "STUDENT_ROLE_NAMES",
    "SelfConflictDenied",
    "audit_self_conflict",
    "build_own_scope",
    "deny_self_conflict",
    "drop_own_scope_cache",
    "guard_self_conflict",
    "is_mixed_student_staff",
    "is_self_conflict",
    "is_student_membership",
    "offering_self_conflict",
    "own_scope",
    "own_scope_excludes",
    "register_own_scope_resolver",
    "self_conflict_message",
    "self_conflict_targets",
]
