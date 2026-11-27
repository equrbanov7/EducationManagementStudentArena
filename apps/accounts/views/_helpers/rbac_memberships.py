"""RBAC — request-ömürlü üzvlük memoizasiyası (``rbac.py``-dən çıxarılıb).

2026-09-13 (Codex audit §14/§21 — kabinet qabığı sorğu büdcəsi). ``rbac.py``
modul-ölçü büdcəsinə (SOFT_CAP 600) dayandığı üçün üzvlük yenidən-istifadəsi və
keş-etibarsızlaşdırma bura köçürülüb; ``rbac.py`` onları yenidən ixrac edir.
Cross-request keş YOXDUR — hər şey ``user`` instansında yaşayır, o isə hər
request-də ``AuthenticationMiddleware`` tərəfindən təzədən yaradılır.
"""

from core.membership_state import has_active_role, membership_epoch


def _bound_active_org_memberships(user, org_id):
    """``OrganizationMiddleware``-in ``user``-ə bağladığı aktiv üzvlük sətirləri —
    YALNIZ eyni təşkilat üçün və yalnız tam siyahıdırsa; əks halda ``None``.

    Kabinet qabığı hər səhifədə eyni ``Membership(user, org, is_active=True)``
    sətirlərini middleware-dən sonra RBAC-da bir də oxuyurdu. Middleware siyahısı
    ``bypass_rls`` ilə oxunur, RBAC isə kirayəçi RLS altında — amma aktiv org =
    RLS tenant olduğu üçün (``rls_tenant_isolation``: ``organization_id = current
    tenant``) nəticə dəsti eynidir. Təhlükəsizlik sərhədləri:

    * Boş siyahı qəbul EDİLMİR — ``_bind_selected_organization`` (superadmin org
      seçimi) qəsdən ``[]`` bağlayır; orada canlı sorğuya düşürük.
    * ``_invalidate_actor_permissions_cache`` çağırılıbsa (eyni request-də
      üzvlük/rol MUTASİYASI) ``_actor_perms_db_only`` bayrağı qalxır və bu
      funksiya həmişə ``None`` qaytarır → köhnə siyahı heç vaxt qayıtmır.
    """
    if (
        getattr(user, "_actor_perms_db_only", False)
        or getattr(user, "_active_membership_epoch", None) != membership_epoch()
    ):
        return None
    bound_org = getattr(user, "_active_organization", None)
    if bound_org is None or getattr(bound_org, "pk", None) != org_id:
        return None
    memberships = getattr(user, "_active_org_memberships", None)
    if not memberships:
        return None
    # `roles.py::_resolve_active_organization_context` ilə eyni süzgəc — yalnız
    # aktiv və məhz bu təşkilata aid sətirlər (siyahı heterogen ola bilməz).
    memberships = [m for m in memberships if has_active_role(m, org_id)]
    return memberships or None


def _invalidate_actor_permissions_cache(user) -> None:
    """Drop the ``_actor_perms_cache`` memoized on ``user`` by ``_collect_actor_permissions``.

    Call this immediately after a code path mutates ``user``'s Membership/Role
    rows (role assignment, membership create/update) so a later permission
    read in the SAME request never returns pre-mutation data. A stale
    permission cache is a security bug, not a perf detail.
    """
    # 2026-09-13: mutasiyadan sonra middleware-in bağladığı üzvlük siyahısı da
    # köhnəlmiş sayılır — bu request-in qalan hissəsi yalnız canlı sorğu ilə.
    # Bayraq ƏVVƏL qalxır ki, aşağıdakı silmə uğursuz olsa belə köhnə siyahı
    # yenidən istifadə olunmasın (fail-closed).
    try:
        user._actor_perms_db_only = True
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass
    try:
        if hasattr(user, "_actor_perms_cache"):
            del user._actor_perms_cache
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass
    # 2026-10-07: middleware-in request üzvlük snapshot-u (scoping/müraciətlər/ana
    # səhifə onu təkrar istifadə edir) da köhnəlib — həmin istehlakçılar canlı sorğuya.
    from apps.organizations.public import drop_request_memberships

    drop_request_memberships(user)


def _collect_actor_permissions(user, organization, *, request=None):
    """
    Return two sets:
    1. effective permissions user currently has in org
    2. explicitly grantable permissions declared as `grant:<permission>` in role permissions

    P1.4 — Per-request memoization (təhlükəsiz):
    Eyni request boyunca eyni (user_id, organization_id) cütü üçün təkrar
    DB sorğusu olmaması üçün nəticə `request._actor_perms_cache` dict-ində
    saxlanılır. Cross-request cache yoxdur — RLS və icazə dəyişiklikləri
    request başında həmişə yenidən qiymətləndirilir.

    QA 2026-09 duplicate-query audit: `_role_capabilities` bu funksiyanı
    HEÇ VAXT `request` ötürmədən çağırır (3x öz daxilində: sual bankı
    axtarışı, müəllim-tələbə idarəsi, "Qruplar" bölməsi qapısı) — yəni yuxarıdakı
    `request`-əsaslı keş faktiki İŞLƏMİRDİ, hər çağırış təzə SELECT idi.
    `request` yoxdursa `user` obyektinə (eyni `apps.applications.services.
    access.active_memberships` naxışı) düşürük — `request.user` bir request
    daxilində SABİT obyektdir (`SimpleLazyObject` bir dəfə həll olunur), ona
    görə bu, faktiki request-ömürlü keşdir, cross-request sızma yoxdur.
    Mutasiya edən yol varsa `_invalidate_actor_permissions_cache(user)` çağırın.
    """
    from apps.organizations.models import Membership

    user_id = getattr(user, "pk", None) or getattr(user, "id", None)
    org_id = getattr(organization, "pk", None) or getattr(organization, "id", None)
    cache_key = (user_id, org_id, membership_epoch())
    cache_owner = request if request is not None else user
    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is None:
            cache = {}
            try:
                cache_owner._actor_perms_cache = cache
            except Exception:  # noqa: BLE001 — request obyekti immutable ola bilər
                cache_owner = None
        if cache_owner is not None and cache_key in cache:
            cached_effective, cached_grantable = cache[cache_key]
            # Cache-i mutasiya etməmək üçün surət qaytarırıq.
            return set(cached_effective), set(cached_grantable)

    effective_permissions = set()
    grantable_permissions = set()

    memberships = _bound_active_org_memberships(user, org_id)
    if memberships is None:  # B21 (2026-10-13): deaktiv rol menyuya açar gətirmir — panel qapısı ilə eyni.
        memberships = Membership.objects.filter(
            user=user, organization=organization, is_active=True, role__is_active=True
        ).select_related("role")
    for membership in (m for m in memberships if getattr(m.role, "is_active", True)):
        for permission in membership.role.permissions or []:
            if permission.startswith("grant:"):
                grantable_permissions.add(permission.split("grant:", 1)[1].strip())
            else:
                effective_permissions.add(permission)

    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is not None:
            cache[cache_key] = (set(effective_permissions), set(grantable_permissions))

    return effective_permissions, grantable_permissions
