"""RBAC — request-ömürlü üzvlük memoizasiyası (``rbac.py``-dən çıxarılıb).

2026-09-13 (Codex audit §14/§21 — kabinet qabığı sorğu büdcəsi). ``rbac.py``
modul-ölçü büdcəsinə (SOFT_CAP 600) dayandığı üçün üzvlük yenidən-istifadəsi və
keş-etibarsızlaşdırma bura köçürülüb; ``rbac.py`` onları yenidən ixrac edir.
Cross-request keş YOXDUR — hər şey ``user`` instansında yaşayır, o isə hər
request-də ``AuthenticationMiddleware`` tərəfindən təzədən yaradılır.
"""


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
    if getattr(user, "_actor_perms_db_only", False):
        return None
    bound_org = getattr(user, "_active_organization", None)
    if bound_org is None or getattr(bound_org, "pk", None) != org_id:
        return None
    memberships = getattr(user, "_active_org_memberships", None)
    if not memberships:
        return None
    # `roles.py::_resolve_active_organization_context` ilə eyni süzgəc — yalnız
    # aktiv və məhz bu təşkilata aid sətirlər (siyahı heterogen ola bilməz).
    memberships = [
        m for m in memberships if getattr(m, "is_active", False) and getattr(m, "organization_id", None) == org_id
    ]
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
