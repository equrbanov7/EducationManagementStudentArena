"""
Mərkəzi unit-scoping servisi.

Dekan / kafedra müdürü kimi UNIT-scope rollu istifadəçilərin görə bildiyi
məlumat sahəsini (öz fakültə/kafedra alt-ağacı) müəyyən edir.

Dizayn prinsipləri:
- `Membership.scope_unit` yeganə mənbədir (source of truth).
- Subtree hesablaması OrgUnit.path (materialized path) üzərində
  `path__startswith` ilə aparılır — rekursiya/N+1 yoxdur.
- Nəticə per-request memoizasiya olunur (`request._unit_scope_cache`) ki,
  sidebar + dashboard + siyahı sorğuları eyni request-də təkrar DB-yə getməsin.
- Cross-request cache QƏSDƏN yoxdur: rol/scope dəyişiklikləri dərhal
  qüvvəyə minməlidir (tenant izolyasiyası > mikro-performans).

TƏK HƏLLEDİCİ (2026-09-12 audit, P1-11). Əvvəl burada İKİ paralel resolver
var idi: köhnə ``get_unit_scope`` (icazəyə baxmadan HƏR aktiv üzvlüyün
``scope_unit``-ini toplayır, ORGANIZATION rolunu yalnız ``level >= 90``
olduqda org-wide sayırdı) və ``get_permission_scope`` (yalnız tələb olunan
açarı DAŞIYAN üzvlükdən əhatə çıxarır). Köhnəsi 14 yerdə işlənirdi və
əlaqəsiz üzvlük (məs. müəllim kimi kafedraya təyinat, tələbə qrupu) öz
unitini imtiyazlı rola «borc verirdi» — 2026-07-31 auditindəki PII sızması
məhz bundan idi. İndi yalnız ``get_permission_scope`` var; hər çağıran
qoruduğu məlumata uyğun icazə açarını AÇIQ verir.
"""

from dataclasses import dataclass, field

from django.db.models import Q, QuerySet

from core.constants import RoleScopeType
from core.permissions import has_permission

#: Köhnə (silinmiş) ümumi resolverin org-wide həddi. Kodda artıq İŞLƏNMİR —
#: yalnız rol kataloqu şərhləri / `test_ikt_rehber_role.py` sənəd kimi istinad
#: edir (RİM rəhbərinin 95 səviyyəsi məhz bu həddə görə seçilib).
ORG_WIDE_MIN_LEVEL = 90


@dataclass(frozen=True)
class UnitScope:
    """
    İstifadəçinin aktiv təşkilatdakı struktur görünüş sahəsi.

    scope_type:
        "org"  — bütün təşkilat (rektor, prorektor, org admin/owner, superadmin,
                 ORGANIZATION-scope idarəetmə rolları, məs. imtahan mərkəzi/HR
                 öz permission-ları çərçivəsində)
        "unit" — yalnız scope_unit alt-ağac(lar)ı (dekan, kafedra müdürü, baş tələbə)
        "none" — struktur görünüşü yoxdur (adi tələbə/müəllim; onların scope-u
                 kurs/qrup üzvlüyü ilə ayrıca müəyyən olunur)
    """

    scope_type: str
    unit_ids: frozenset = field(default_factory=frozenset)
    unit_paths: tuple = field(default_factory=tuple)

    @property
    def is_org_wide(self) -> bool:
        return self.scope_type == "org"

    @property
    def is_unit_scoped(self) -> bool:
        return self.scope_type == "unit"

    @property
    def has_structure_access(self) -> bool:
        return self.scope_type in {"org", "unit"}

    def unit_subtree_q(self, path_field: str = "path", id_field: str = "id") -> Q:
        """
        OrgUnit queryset-i üçün alt-ağac filtri (öz unitlər + bütün törəmələri).
        Boş scope üçün heç nə uyğun gəlməyən Q qaytarır.
        """
        if self.is_org_wide:
            return Q()
        if not self.unit_paths:
            return Q(pk__in=[])
        q = Q(**{f"{id_field}__in": list(self.unit_ids)})
        for path in self.unit_paths:
            q |= Q(**{f"{path_field}__startswith": f"{path}/"})
        return q


ORG_WIDE_SCOPE = UnitScope(scope_type="org")
EMPTY_SCOPE = UnitScope(scope_type="none")


def _permission_scope_memberships(user, organization) -> list:
    """Active memberships used to resolve ``get_permission_scope`` — memoized on ``user``.

    QA 2026-09 duplicate-query audit: ``_role_capabilities`` calls
    ``get_permission_scope`` up to 6x per build (course.edit, journal.close,
    journal.roster, final_score.entry, analytics.view_all, analytics.view_unit)
    for the SAME (user, organization) — every call re-ran this exact SELECT
    because the request-level cache below is keyed by permission and the
    caller (``apps/accounts/views/_helpers/rbac.py``) never threads a
    ``request`` through. Memoizing the membership rows themselves — same
    object-attribute pattern as ``apps.applications.services.access.
    active_memberships`` — collapses those 6 queries into 1, independent of
    whether a ``request`` is available.

    No cross-request cache: the attribute lives on the ``user`` instance,
    which Django/AuthenticationMiddleware re-creates fresh from the DB at the
    start of every request. Any code path that mutates this user's
    memberships/roles within the SAME request must call
    ``invalidate_permission_scope_cache(user)`` afterwards.
    """
    from apps.organizations.models import Membership

    from .request_memberships import request_active_memberships

    org_pk = getattr(organization, "pk", None)
    cache = getattr(user, "_org_scope_memberships_cache", None)
    if cache is not None and org_pk in cache:
        return cache[org_pk]
    # Perf 2026-10-07: middleware-in eyni request-də oxuduğu sətirlər (eyni süzgəc,
    # `role__is_active` Python-da) — yararsızdırsa canlı sorğu. Sıra əhəmiyyətsizdir.
    snapshot = request_active_memberships(user, organization)
    if snapshot is not None:
        memberships = [membership for membership in snapshot if membership.role.is_active]
    else:
        memberships = list(
            Membership.objects.filter(
                user=user,
                organization=organization,
                is_active=True,
                role__organization=organization,
                role__is_active=True,
            ).select_related("role", "scope_unit")
        )
    if cache is None:
        cache = {}
        try:
            user._org_scope_memberships_cache = cache
        except Exception:  # noqa: BLE001 — bəzi user obyektləri immutable ola bilər (məs. AnonymousUser)
            cache = None
    if cache is not None:
        cache[org_pk] = memberships
    return memberships


def _resolve_active_unit_paths(user, organization, unit_ids) -> list:
    """Resolve ``(pk, path)`` rows for active org units — memoized per (org, unit_ids).

    For UNIT-scoped roles (dean, chair_head), ``get_permission_scope`` calls
    this once per permission checked; the qualifying ``unit_ids`` set is often
    IDENTICAL across those calls (same membership, several permissions on its
    role), so without memoization this ``OrgUnit`` lookup repeats 6-11x per
    ``_role_capabilities`` build (QA 2026-09 audit). Keyed by the exact
    ``unit_ids`` set (not just org) because different permissions can
    legitimately resolve to different qualifying units.
    """
    from apps.organizations.models import OrgUnit

    org_pk = getattr(organization, "pk", None)
    key = (org_pk, frozenset(unit_ids))
    cache = getattr(user, "_org_scope_unit_paths_cache", None)
    if cache is not None and key in cache:
        return cache[key]
    resolved = list(
        OrgUnit.objects.filter(organization=organization, pk__in=unit_ids, is_active=True).values_list("pk", "path")
    )
    if cache is None:
        cache = {}
        try:
            user._org_scope_unit_paths_cache = cache
        except Exception:  # noqa: BLE001 — bəzi user obyektləri immutable ola bilər
            cache = None
    if cache is not None:
        cache[key] = resolved
    return resolved


def invalidate_permission_scope_cache(user) -> None:
    """Drop the memoized membership rows kept by ``_permission_scope_memberships``
    and ``_resolve_active_unit_paths``.

    Call this immediately after a code path mutates ``user``'s Membership/Role
    rows (role assignment, membership create/update) so a later
    ``get_permission_scope`` read in the SAME request never returns
    pre-mutation data. A stale permission cache is a security bug, not a perf
    detail — see the module docstring.
    """
    from .request_memberships import drop_request_memberships

    for attr in ("_org_scope_memberships_cache", "_org_scope_unit_paths_cache"):
        try:
            if hasattr(user, attr):
                delattr(user, attr)
        except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
            pass
    # Middleware-in request üzvlük snapshot-u da (bax `request_memberships`).
    drop_request_memberships(user)


def has_active_membership_permission(user, organization, permission: str) -> bool:
    """Check a membership grant using the same request snapshot as unit scopes.

    COURSE grants intentionally qualify even though they grant no structural
    scope. Owners/superadmins receive no implicit grant here: instructor
    eligibility requires a real active same-tenant membership and role.
    """
    if not permission:
        raise ValueError("membership permission key is required")
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or organization is None
        or not organization.is_active
    ):
        return False
    return any(
        has_permission(list(membership.role.permissions or []), permission)
        for membership in _permission_scope_memberships(user, organization)
    )


def get_permission_scope(user, organization, permission: str, request=None) -> UnitScope:
    """Resolve structural scope only from memberships granting ``permission``.

    A UNIT-scoped role without a valid ``scope_unit`` grants no structural
    access.  An unrelated membership must never lend its unit to a privileged
    role — the legacy generic resolver that did so was removed (P1-11,
    2026-09-12), so this is now the ONLY scope resolver.

    Müqavilə (çağıranlar üçün):
      * superadmin / təşkilat sahibi → ``ORG_WIDE_SCOPE`` (açardan asılı deyil);
      * açarı daşıyan ORGANIZATION rolu → ``ORG_WIDE_SCOPE`` (səviyyə YOX);
      * açarı daşıyan UNIT rolu + etibarlı ``scope_unit`` → həmin alt-ağac(lar);
      * COURSE rolu, açarsız rol, ``scope_unit``-siz UNIT rolu → ``EMPTY_SCOPE``
        (fail-closed). ``permission`` boş ola BİLMƏZ.
    ``request`` verilərsə nəticə ``request._unit_scope_cache``-də açar üzrə
    saxlanılır; üzvlük sətirləri isə ``user`` obyektində memoizasiya olunur.
    """
    if not permission:
        # Boş açar «hər şeyə icazə» kimi oxuna bilməz — səssiz ORG_WIDE əvəzinə
        # proqramçı xətası kimi dərhal partlayır (fail-closed).
        raise ValueError("get_permission_scope: `permission` açarı boş ola bilməz")
    user_id = getattr(user, "pk", None)
    org_id = getattr(organization, "pk", None)
    cache_key = ("permission", user_id, org_id, permission)
    if request is not None:
        cache = getattr(request, "_unit_scope_cache", None)
        if cache is None:
            cache = {}
            request._unit_scope_cache = cache
        if cache_key in cache:
            return cache[cache_key]

    if not user or not getattr(user, "is_authenticated", False) or organization is None:
        scope = EMPTY_SCOPE
    elif getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        scope = ORG_WIDE_SCOPE
    elif getattr(organization, "owner_id", None) == user_id:
        scope = ORG_WIDE_SCOPE
    else:
        memberships = _permission_scope_memberships(user, organization)
        unit_ids = set()
        scope = EMPTY_SCOPE
        for membership in memberships:
            role = membership.role
            if not has_permission(list(role.permissions or []), permission):
                continue
            if role.scope_type == RoleScopeType.ORGANIZATION:
                scope = ORG_WIDE_SCOPE
                break
            if role.scope_type == RoleScopeType.UNIT and membership.scope_unit_id:
                unit_ids.add(membership.scope_unit_id)
        if not scope.is_org_wide and unit_ids:
            resolved = _resolve_active_unit_paths(user, organization, unit_ids)
            if resolved:
                scope = UnitScope(
                    scope_type="unit",
                    unit_ids=frozenset(pk for pk, _path in resolved),
                    unit_paths=tuple(path for _pk, path in resolved if path),
                )

    if request is not None:
        request._unit_scope_cache[cache_key] = scope
    return scope


#: Oxu genişlənməsinin tipləri (``faculty_read_scope``). Fakültə DAXİLİNDƏKİ akademik vahidlər — kafedra
#: (``department`` da kafedradır), ixtisas, qrup, dekanlıq — ən yaxın aktiv FAKÜLTƏ əcdadına genişlənir.
#: Digər tiplər (inzibati bölmə, mərkəz …) QƏSDƏN siyahıda deyil: onların əhatəsi olduğu kimi qalır.
_FACULTY_UNIT_TYPE = "faculty"
_WIDEN_TO_FACULTY_TYPES = frozenset({"chair", "department", "specialty", "group", "deanery"})


def unit_in_scope(scope: UnitScope, unit) -> bool:
    """Vahid (``pk`` + ``path`` yüklü) əhatənin içindədirmi — SORĞUSUZ (sətir səviyyəli UI bayraqları üçün).

    ``unit_subtree_q`` ilə eyni qayda: org-wide → bəli; unit əhatəsi → kök özü və ya ``<kök yolu>/`` ilə
    başlayan yol; əhatəsiz / ``None`` → yox (fail-closed).
    """
    if unit is None:
        return False
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    if getattr(unit, "pk", None) in scope.unit_ids:
        return True
    path = str(getattr(unit, "path", "") or "")
    if not path:
        return False
    return any(path == root or path.startswith(f"{root}/") for root in scope.unit_paths if root)


def widen_chair_scope_to_faculty(organization, scope: UnitScope, request=None) -> UnitScope:
    """Unit əhatəsindəki fakültə-daxili kökləri (kafedra / ixtisas / qrup / dekanlıq) ən yaxın FAKÜLTƏ ilə əvəz edir.

    2026-10-14 (sahib, tyutor kimi baxış): «tyutor ancaq özünün aid olduğu fakültəni görsün … tyutor və proqram
    koordinatoru eyni vəzifədir, adətən fakültə dekanlığı tərkibində olur». Qayda ROL ADINA deyil, üzvlüyün
    ``scope_unit`` TİPİNƏ baxır — kafedra müdiri, tyutor, koordinator eyni cür genişlənir. Fakültə əcdadı
    olmayan (və ya fakültəsi passiv) vahid və siyahıda olmayan tiplər olduğu kimi qalır; nəticə ilkin əhatəni
    həmişə ƏHATƏ EDİR (yalnız genişlənir). Org-wide / boş əhatə dəyişmir. Ən çoxu İKİ sorğu, request-ə yaddaş.
    """
    if not scope.is_unit_scoped or organization is None:
        return scope
    cache_key = ("faculty_read", getattr(organization, "pk", None), scope.unit_ids)
    cache = getattr(request, "_unit_scope_cache", None) if request is not None else None
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    from apps.organizations.models import OrgUnit

    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=list(scope.unit_ids)).only("id", "path", "unit_type")
    )
    ancestor_ids = {
        part
        for unit in units
        if unit.unit_type in _WIDEN_TO_FACULTY_TYPES
        for part in str(unit.path or "").split("/")[:-1]
        if part
    }
    faculties = {}
    if ancestor_ids:
        faculties = {
            str(pk): (pk, path)
            for pk, path in OrgUnit.objects.filter(
                organization=organization, pk__in=list(ancestor_ids), unit_type=_FACULTY_UNIT_TYPE, is_active=True
            ).values_list("pk", "path")
        }
    roots = {}
    for unit in units:
        faculty = None
        if unit.unit_type in _WIDEN_TO_FACULTY_TYPES:
            # Ən YAXIN fakültə əcdadı (yol kökdən aşağı gedir — tərsinə axtarılır).
            for part in reversed(str(unit.path or "").split("/")[:-1]):
                if part in faculties:
                    faculty = faculties[part]
                    break
        if faculty is not None:
            roots[faculty[0]] = faculty[1]
        else:
            roots[unit.pk] = unit.path
    widened = UnitScope(
        scope_type="unit", unit_ids=frozenset(roots), unit_paths=tuple(path for path in roots.values() if path)
    )
    if cache is not None:
        cache[cache_key] = widened
    return widened


def faculty_read_scope(user, organization, permission: str, request=None) -> UnitScope:
    """OXU əhatəsi: ``get_permission_scope`` + fakültə-daxili köklər (kafedra/ixtisas/qrup) FAKÜLTƏYƏ genişlənir.

    Sahib (2026-10-14, kafedra müdiri kimi baxış): «kafedra müdiri də öz fakültəsi daxilindəki
    tələbələri görə bilsin», «Qruplar / İxtisaslar — ancaq öz fakültəmizə aid olanı». Bu
    universitetdə ixtisas və qruplar KAFEDRANIN deyil, FAKÜLTƏNİN altındadır — kafedra alt-ağacında
    nə qrup, nə ixtisas, nə tələbə var. 2026-10-14 (axşam): tyutor / proqram koordinatoru da (fakültə,
    kafedra, ixtisas və ya qrupa təyin olunsa belə) öz FAKÜLTƏSİNİ görür. YALNIZ oxu səthləri (tələbə
    kataloqu, «Tələbə reyestri», qrup reyestri, struktur ağacı, ixtisaslar, fənn kataloqu) bu helper-i
    işlədir; YAZI əməlləri (``unit.group_manage``, ``catalog.manage``, ``people.manage_*``,
    ``student.movement``) həmişə dar ``get_permission_scope`` ilə qalır.
    """
    scope = get_permission_scope(user, organization, permission, request=request)
    return widen_chair_scope_to_faculty(organization, scope, request=request)


def permission_scope_unit_types(user, organization, permission: str) -> frozenset:
    """``permission`` açarını daşıyan UNIT üzvlüklərinin ``scope_unit`` TİPLƏRİ (sorğusuz).

    2026-10-14 (sahib: «kafedra müdiri səhifəsində Fakültələrə ehtiyac yoxdur»): bölmə görünürlüyü
    əhatənin NÖVÜNƏ baxır. Üzvlük sətirləri ``get_permission_scope``-un memoizasiya etdiyi
    (``scope_unit`` yüklü) siyahıdandır — kabinet qabığına əlavə sorğu YOXDUR.
    """
    return frozenset(unit.unit_type for unit in permission_scope_units(user, organization, permission))


def permission_scope_units(user, organization, permission: str) -> tuple:
    """``permission`` açarını daşıyan UNIT üzvlüklərinin AKTİV ``scope_unit`` obyektləri (sorğusuz, təkrarsız).

    2026-10-24 (sahib): əhatənin kökü KAFEDRA olanda (``journal.view`` — jurnal siyahısı/müşahidə) qrup
    alt-ağacı boşdur — çağıran kökün tipinə görə əlavə qayda qurur. Sətirlər ``get_permission_scope``-un
    memoizasiya etdiyi (``scope_unit`` yüklü) üzvlüklərdəndir — əlavə sorğu YOXDUR. Org-wide qərarını
    VERMİR: çağıran əvvəl ``get_permission_scope`` ilə yoxlamalıdır.
    """
    if not permission or organization is None or not getattr(user, "is_authenticated", False):
        return ()
    units: dict = {}
    for membership in _permission_scope_memberships(user, organization):
        role = membership.role
        if role.scope_type != RoleScopeType.UNIT or not membership.scope_unit_id:
            continue
        if not has_permission(list(role.permissions or []), permission):
            continue
        unit = membership.scope_unit
        if unit is not None and unit.is_active:
            units.setdefault(unit.pk, unit)
    return tuple(units.values())


def scope_org_units(queryset: QuerySet, scope: UnitScope) -> QuerySet:
    """OrgUnit queryset-ini scope-a görə məhdudlaşdırır."""
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q())


def scope_memberships_by_unit(queryset: QuerySet, scope: UnitScope, organization=None) -> QuerySet:
    """
    Membership queryset-ini scope-a görə məhdudlaşdırır:
    yalnız scope alt-ağacındakı unitlərə bağlı üzvlüklər görünür.

    Performans: alt-ağac unit id-ləri tək subquery ilə alınır;
    Membership üzərində scope_unit__in filtri index-lənmiş FK-dır.
    """
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()

    from apps.organizations.models import OrgUnit

    subtree_unit_ids = OrgUnit.objects.filter(scope.unit_subtree_q())
    if organization is not None:
        subtree_unit_ids = subtree_unit_ids.filter(organization=organization)
    return queryset.filter(scope_unit__in=subtree_unit_ids.values("pk"))


__all__ = [
    "EMPTY_SCOPE",
    "faculty_read_scope",
    "ORG_WIDE_SCOPE",
    "ORG_WIDE_MIN_LEVEL",
    "UnitScope",
    "get_permission_scope",
    "invalidate_permission_scope_cache",
    "permission_scope_unit_types",
    "permission_scope_units",
    "scope_memberships_by_unit",
    "scope_org_units",
    "unit_in_scope",
    "user_scope_covers_unit",
    "user_scope_subtree_q",
    "widen_chair_scope_to_faculty",
]


def user_scope_subtree_q(user, organization, *, path_field, id_field, permission):
    """İstifadəçinin ``permission`` əhatəsi üçün filtr Q-su — ixtiyari sahə prefiksi ilə.

    `user_scope_covers_unit` bir unit üçün bool qaytarır; siyahı/aqreqat
    sorğularını daraltmaq üçünsə QUERYSET filtri lazımdır. Məsələn analitika
    `Enrollment`-ləri `offering__group` üzərindən daraldır:

        user_scope_subtree_q(u, org,
                             path_field="offering__group__path",
                             id_field="offering__group__id",
                             permission="analytics.view_unit")

    Nəticə ``UnitScope.unit_subtree_q`` ilə eynidir: org-wide → boş ``Q()``
    (filtr yoxdur), alt-ağac → subtree filtri, əhatəsiz → ``Q(pk__in=[])``
    (fail-closed, heç nə uyğun gəlmir).

    2026-09-12 (P1-11): ``permission`` artıq MƏCBURİDİR. Əvvəlki açarsız qol
    köhnə ümumi resolveri işlədib ``None`` («filtr tətbiq etmə») qaytarırdı;
    layihədə o qolun heç bir çağıranı qalmamışdı və resolver silindi.
    """
    scope = get_permission_scope(user, organization, permission)
    return scope.unit_subtree_q(path_field=path_field, id_field=id_field)


def user_scope_covers_unit(user, organization, unit_id, permission) -> bool:
    """İstifadəçinin ``permission`` əhatəsi verilmiş bölməni əhatə edirmi (fail-closed).

    MODUL SƏRHƏDİ: bu yoxlama registrar-dan (jurnal təsdiqi) lazımdır, lakin
    registrar ``apps.organizations``-u Python səviyyəsində İMPORT ETMİR — əks
    halda ``organizations ↔ registrar`` dövrü yaranır (organizations seed əmri
    registrar-ı import edir). Registrar organizations modellərini yalnız app
    registry ilə həll edir (bax ``apps/registrar/public.py`` şərhinə), ona görə
    məntiq burada, öz modulunda qalır və modeldən nazik delegator ilə çağırılır.

    * əhatə yoxdursa (``has_structure_access`` yalan) → ``False``;
    * org-wide → ``True``;
    * ``unit_id`` ``None``-dursa ``False`` — unit-scope istifadəçi üçün
      aidiyyəti müəyyən deyil, org-wide səlahiyyət tələb olunur.

    2026-09-12 (P1-11): ``permission`` MƏCBURİDİR; köhnə açarsız qol («scope
    təyin edilməyibsə True») ümumi resolverlə birlikdə silindi — çağıranı
    qalmamışdı (syllabus/workload/registrar hamısı açar ötürür).
    """
    from .models import OrgUnit

    scope = get_permission_scope(user, organization, permission)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    if unit_id is None:
        return False
    return OrgUnit.objects.filter(scope.unit_subtree_q()).filter(pk=unit_id).exists()
