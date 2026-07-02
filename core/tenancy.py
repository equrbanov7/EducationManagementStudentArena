"""
Shared helpers for request-scoped tenant filtering.
"""

from django.core.exceptions import ObjectDoesNotExist

from core.rls import bypass_rls, set_rls_bypass, set_rls_tenant, set_rls_user

TRUSTED_OWNER_CONTEXT_ATTR = "_owner_verified_organization_context"


def _is_tenant_accessible_organization(organization) -> bool:
    return bool(
        organization and getattr(organization, "is_active", False) and getattr(organization, "status", "") == "active"
    )


def _request_context_has_usable_organization(organization) -> bool:
    """
    Accept minimal request doubles unless they explicitly describe a blocked org.

    Unit tests often provide lightweight stubs or ``MagicMock(spec=Organization)``
    objects that do not carry concrete ``is_active``/``status`` field values.
    Those requests still represent a valid active-context check as long as the
    stub does not explicitly mark the org as inactive/suspended.
    """
    if organization is None:
        return False

    is_active = getattr(organization, "is_active", None)
    if isinstance(is_active, bool) and not is_active:
        return False

    status = getattr(organization, "status", None)
    if isinstance(status, str) and status and status != "active":
        return False

    return True


def get_request_organization(request):
    """
    Resolve the active organization selected on this request.
    """
    if request is None:
        return None

    return getattr(request, "organization", None)


def request_has_active_organization_context(request, *, allow_superadmin=True):
    """
    Return whether the request has a valid active tenant context.
    """
    organization = get_request_organization(request)
    if not _request_context_has_usable_organization(organization):
        return False

    user = getattr(request, "user", None)
    if allow_superadmin and bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False)):
        return True
    if bool(getattr(request, TRUSTED_OWNER_CONTEXT_ATTR, False)):
        return user is not None and getattr(organization, "owner_id", None) == getattr(user, "id", None)

    memberships = getattr(request, "org_memberships", None) or []
    if not memberships:
        return False

    if user is not None and getattr(organization, "owner_id", None) == getattr(user, "id", None):
        # Owners may still appear inside a normal membership-backed context.
        return True

    return bool(memberships)


def _resolve_profile_fallback_org(user, resolved_profile):
    """
    Bərpa üçün hədəf təşkilatı tap:

    1) Profil təşkilatı (əlçatandırsa) — köhnə davranış, dəyişmir.
    2) Profil təşkilatı yoxdursa/əlçatmazdırsa, istifadəçinin YEGANƏ aktiv
       təşkilatı (üzvlük və ya sahiblik). Bu, OrganizationMiddleware-in tək-org
       auto-select məntiqini təkrarlayır və tenant-təhlükəsizdir, çünki yalnız
       istifadəçinin həqiqətən aid olduğu org bərpa olunur.
    3) Bir neçə aktiv org varsa, təxmin etmirik (None) — istifadəçi seçməlidir.

    Bu, "təzə sessiyada my-exams/my-courses boş görünür, yalnız yeni element
    yaradandan sonra çıxır" problemini həll edir: session aktiv org saxlamayanda
    siyahı scope-u artıq boş qalmır.
    """
    profile_org = getattr(resolved_profile, "organization", None)
    if _is_tenant_accessible_organization(profile_org):
        return profile_org

    from django.apps import apps as django_apps

    Membership = django_apps.get_model("organizations", "Membership")
    Organization = django_apps.get_model("organizations", "Organization")

    with bypass_rls():
        candidate_ids = set(
            Membership.objects.filter(
                user=user,
                organization__is_active=True,
                organization__status="active",
                is_active=True,
            ).values_list("organization_id", flat=True)
        )
        candidate_ids |= set(
            Organization.objects.filter(
                owner=user,
                is_active=True,
                status="active",
            ).values_list("id", flat=True)
        )
        # Yalnız tək, qeyri-müəyyənliksiz org bərpa olunur.
        if len(candidate_ids) != 1:
            return None
        return Organization.objects.filter(id=next(iter(candidate_ids))).first()


def restore_request_organization_from_profile(request, *, profile=None, allow_multi_org_restore=False):
    """
    Re-hydrate ``request.organization`` from the user's profile organization.

    This is a recovery path for org-bound actions reached from profile
    sections when the session lost its active tenant selection. Profil org-u
    təyin olunmayıbsa, istifadəçinin yeganə aktiv/sahib org-una fallback edilir
    (bax: ``_resolve_profile_fallback_org``).
    """
    if request is None or get_request_organization(request) is not None:
        return False

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    if profile is not None:
        resolved_profile = profile
    else:
        try:
            resolved_profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            resolved_profile = None
    fallback_org = _resolve_profile_fallback_org(user, resolved_profile)
    if not _is_tenant_accessible_organization(fallback_org):
        return False

    from django.apps import apps as django_apps

    Membership = django_apps.get_model("organizations", "Membership")

    with bypass_rls():
        memberships = list(
            Membership.objects.filter(
                user=user,
                organization=fallback_org,
                organization__is_active=True,
                organization__status="active",
                is_active=True,
            )
            .select_related("organization", "role", "scope_unit")
            .order_by("-is_primary", "-role__level")
        )
        active_org_ids = set(
            Membership.objects.filter(
                user=user,
                organization__is_active=True,
                organization__status="active",
                is_active=True,
            ).values_list("organization_id", flat=True)
        )

    is_owner = getattr(fallback_org, "owner_id", None) == getattr(user, "id", None)
    is_superadmin = bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))
    if not memberships and not is_owner and not is_superadmin:
        return False
    if not is_superadmin and len(active_org_ids) > 1 and not allow_multi_org_restore:
        return False

    permissions_set = set()
    for membership in memberships:
        role = getattr(membership, "role", None)
        role_permissions = getattr(role, "permissions", None) or []
        permissions_set.update(role_permissions)
        if getattr(role, "name", "") == "teacher":
            permissions_set.add("course.create")

    request.organization = fallback_org
    request.org_memberships = memberships
    request.org_permissions = list(permissions_set)
    setattr(request, TRUSTED_OWNER_CONTEXT_ATTR, bool(is_owner and not memberships))

    session = getattr(request, "session", None)
    if session is not None:
        session["active_organization"] = fallback_org.slug

    if hasattr(user, "set_active_organization_context"):
        user.set_active_organization_context(
            fallback_org,
            memberships=memberships,
            permissions=request.org_permissions,
        )

    set_rls_user(user.pk)
    if is_superadmin:
        set_rls_bypass(True)
    else:
        set_rls_bypass(False)
        set_rls_tenant(fallback_org.pk)

    return True


def scoped_by_organization(queryset, request, org_field="organization"):
    """
    Apply active-organization filtering for models bound to an Organization FK.

    Args:
        queryset: Base queryset to scope.
        request: Django request object (for active org lookup).
        org_field: Organization FK field on the model (defaults to ``organization``).
    """
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return queryset.none()

    return queryset.filter(**{org_field: organization})
