"""
"View as" endpoint-ləri: istifadəçi axtarışı (JSON), başlatma və bitirmə.

Bütün icazə məntiqi ``services.view_as``-dadır; burada yalnız HTTP qatı var.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from core.rls import bypass_rls

from ...models import ProfileRole
from ...services.view_as import (
    SEARCH_PAGE_SIZE,
    build_target_queryset,
    resolve_actor_access,
    start_view_as,
    stop_view_as,
    validate_target,
)
from .._helpers import PROFILE_ROLE_LABELS


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def _load_active_org_by_pk(raw_pk):
    """UUID pk-nı təhlükəsiz yüklə (yanlış format → None, exception yox)."""
    raw_pk = (raw_pk or "").strip()
    if not raw_pk or len(raw_pk) > 64:
        return None
    from apps.organizations.models import Organization

    try:
        with bypass_rls():
            return Organization.objects.filter(pk=raw_pk, is_active=True, status="active").first()
    except (TypeError, ValueError, ValidationError):
        return None


def _resolve_search_organization(request):
    """Axtarış üçün org: superadmin `org` parametri seçir, qalanlar aktiv org."""
    if _is_superadmin(request.user):
        return _load_active_org_by_pk(request.GET.get("org"))
    return getattr(request, "organization", None)


def _serialize_users(page_users, organization):
    """Səhifədəki istifadəçilər üçün rol etiketlərini TƏK sorğu ilə yığ (N+1 yox)."""
    from apps.organizations.models import Membership

    user_ids = [user.pk for user in page_users]
    role_map = {}
    if user_ids:
        memberships = (
            Membership.objects.filter(organization=organization, user_id__in=user_ids, is_active=True)
            .select_related("role")
            .order_by("-role__level")
        )
        for membership in memberships:
            normalized = ProfileRole.normalize_membership_role_name(getattr(membership.role, "name", "") or "")
            label = PROFILE_ROLE_LABELS.get(
                normalized, (getattr(membership.role, "name", "") or "").replace("_", " ").title()
            )
            role_map.setdefault(membership.user_id, [])
            if label not in role_map[membership.user_id]:
                role_map[membership.user_id].append(label)

    results = []
    for user in page_users:
        full_name = (f"{user.first_name} {user.last_name}").strip() or user.username
        results.append(
            {
                "id": user.pk,
                "name": full_name,
                "username": user.username,
                "email": user.email,
                "roles": role_map.get(user.pk, [])[:3],
                "avatar_url": reverse("accounts:profile_avatar", args=[user.pk]),
            }
        )
    return results


@login_required
@require_GET
def view_as_search(request):
    """
    JSON axtarış endpoint-i.

    ``type=orgs`` (yalnız superadmin) → təşkilat siyahısı.
    ``type=users`` (default) → seçilmiş org daxilində icazəli hədəflər.
    """
    # Aktiv view-as sessiyası içində panel yoxdur → nested keçid qadağandır.
    if getattr(request, "is_view_as", False):
        return JsonResponse({"detail": "forbidden"}, status=403)

    search_type = (request.GET.get("type") or "users").strip()
    q = (request.GET.get("q") or "").strip()[:120]

    if search_type == "orgs":
        if not _is_superadmin(request.user):
            return JsonResponse({"detail": "forbidden"}, status=403)
        from apps.organizations.models import Organization

        with bypass_rls():
            org_qs = Organization.objects.filter(is_active=True, status="active")
            if q:
                org_qs = org_qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
            orgs = list(org_qs.order_by("name").values("id", "name", "org_type")[:30])
        return JsonResponse({"results": orgs})

    organization = _resolve_search_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False, "detail": "no_organization"}, status=400)

    mode, actor_level, memberships = resolve_actor_access(request.user, organization)
    if mode is None:
        return JsonResponse({"detail": "forbidden"}, status=403)

    page = request.GET.get("page") or "1"
    page = int(page) if page.isdigit() and 0 < int(page) <= 500 else 1
    offset = (page - 1) * SEARCH_PAGE_SIZE

    users_qs = build_target_queryset(
        request.user,
        organization,
        mode=mode,
        actor_level=actor_level,
        memberships=memberships,
        q=q,
        role_filter=request.GET.get("role") or "",
    )

    def _fetch():
        # +1 → has_more üçün; COUNT(*) sorğusuna ehtiyac qalmır.
        chunk = list(users_qs[offset : offset + SEARCH_PAGE_SIZE + 1])
        has_more = len(chunk) > SEARCH_PAGE_SIZE
        return chunk[:SEARCH_PAGE_SIZE], has_more

    if actor_level >= 999:
        with bypass_rls():
            page_users, has_more = _fetch()
            results = _serialize_users(page_users, organization)
    else:
        page_users, has_more = _fetch()
        results = _serialize_users(page_users, organization)

    return JsonResponse({"results": results, "has_more": has_more, "mode": mode, "page": page})


@login_required
@require_POST
def view_as_start(request):
    """Seçilmiş istifadəçinin profilinə keçid (view-as sessiyası başladır)."""
    if getattr(request, "is_view_as", False):
        messages.warning(request, pgettext("accounts.view_as", "not_allowed"))
        return redirect("accounts:profile")

    if _is_superadmin(request.user):
        organization = _load_active_org_by_pk(request.POST.get("org"))
    else:
        organization = getattr(request, "organization", None)

    target, mode = (None, None)
    if organization is not None:
        target, mode = validate_target(request.user, organization, request.POST.get("user_id"))

    if target is None:
        messages.error(request, pgettext("accounts.view_as", "not_allowed"))
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    start_view_as(request, target, organization, mode)

    display_name = (f"{target.first_name} {target.last_name}").strip() or target.username
    if mode == "readonly":
        message_template = pgettext("accounts.view_as", "started_readonly")
    else:
        message_template = pgettext("accounts.view_as", "started_full")
    try:
        messages.info(request, message_template % {"name": display_name})
    except (KeyError, TypeError, ValueError):
        messages.info(request, message_template)

    return redirect(f"{reverse('accounts:profile')}?section=profile-info")


@login_required
@require_POST
def view_as_stop(request):
    """View-as sessiyasını bitirib öz profilə qayıdır."""
    stop_view_as(request)
    messages.success(request, pgettext("accounts.view_as", "stopped"))
    return redirect(f"{reverse('accounts:profile')}?section=profile-info")
