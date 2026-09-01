"""
Public user profile view.

Renders a user's public profile: only published posts and non-confidential
profile information are exposed. Safe for anonymous visitors.

M2 (2026-07-02): post siyahısı/filtr məntiqi blog-a köçüb —
profile_hooks.public_posts_context (apps/blog/profile_sections.py).
"""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_safe

from core.permissions import is_superadmin_user
from core.staff_position import resolve_position_label
from core.tenancy import get_request_organization

from ... import profile_hooks
from ...models import UserProfile

User = get_user_model()

#: Təşkilat Role şkalasında (seed: student=10, teacher=50, dean=80, owner=100)
#: «əməkdaş» hesab olunan minimum səviyyə — müəllim və yuxarı. DİQQƏT: bu,
#: core.constants.ROLE_LEVEL_TEACHER (60, ProfileRole şkalası) İLƏ EYNİ DEYİL.
_STAFF_ROLE_MIN_LEVEL = 50


def _admin_membership_for_viewer(request, profile_user):
    """
    Rol/email/qoşulma tarixi kartını yalnız haçansa göstər: baxan istifadəçi
    öz aktiv təşkilatında bu şəxsin üzvlərini görmək icazəsinə malikdirsə
    (Struktur üzvləri / Audit jurnalı üzərindən gələn admin baxışı üçün).
    """
    if not request.user.is_authenticated:
        return None

    viewer_org = get_request_organization(request)
    if viewer_org is None:
        return None

    from apps.organizations.views.shared._helpers import _can_manage_organization, _has_org_permission

    can_view_members = (
        is_superadmin_user(request.user)
        or _can_manage_organization(request.user, viewer_org)
        or _has_org_permission(request, "member.view")
    )
    if not can_view_members:
        return None

    return (
        profile_user.memberships.filter(organization=viewer_org, is_active=True)
        .select_related("role", "scope_unit")
        .order_by("-role__level")
        .first()
    )


def _viewer_can_see_contact(request, profile_user):
    """Telefon nömrələri yalnız EYNİ təşkilatın əməkdaş səviyyəli üzvünə görünür.

    Tələbə və anonim baxanlara HEÇ VAXT göstərilmir; sahibi öz önizləməsində
    görür ki, nəyin dərc olunduğunu bilsin. Tenant-scoped: baxanın profil
    sahibinin aktiv üzv olduğu təşkilatlardan birində müəllim+ (level ≥ 60)
    AKTİV üzvlüyü olmalıdır — kənar təşkilatın müəllimi və şəxsi (INDIVIDUAL)
    workspace sahibi görmür (2026-08-15 review tapıntısı).
    """
    if not request.user.is_authenticated:
        return False
    if request.user == profile_user:
        return True
    if is_superadmin_user(request.user):
        return True

    from apps.organizations.models import Membership

    profile_org_ids = Membership.objects.filter(user=profile_user, is_active=True).values_list(
        "organization_id", flat=True
    )
    return Membership.objects.filter(
        user=request.user,
        is_active=True,
        organization_id__in=profile_org_ids,
        role__level__gte=_STAFF_ROLE_MIN_LEVEL,
    ).exists()


@require_safe
def public_user_profile(request, username):
    """
    Public user profile showing only published posts and non-confidential
    profile information.

    ``?preview=1`` — sahibin öz profilinin kənardan necə göründüyünə baxışı
    (redaktə səhifəsindəki «Önizləmə» düyməsi); yalnız öz profilində keçərlidir.
    """
    profile_user = get_object_or_404(User, username=username)

    is_self = request.user.is_authenticated and request.user == profile_user
    is_self_preview = is_self and request.GET.get("preview") == "1"
    if is_self and not is_self_preview:
        return redirect("accounts:profile")

    profile, _created = UserProfile.objects.get_or_create(user=profile_user)

    posts_result = profile_hooks.public_posts_context(request, profile_user)
    if posts_result["response"] is not None:
        return posts_result["response"]

    display_name = (f"{profile_user.first_name} {profile_user.last_name}").strip() or profile_user.username

    from ...services import academic_profile

    contact_phones = []
    if _viewer_can_see_contact(request, profile_user):
        contact_phones = [phone for phone in (profile.phone, profile.phone_secondary) if (phone or "").strip()]

    admin_membership = _admin_membership_for_viewer(request, profile_user)
    # ⚠️ Vəzifə zənciri: Membership.title → UserProfile.staff_position → real rol.
    # Doldurucu «Üzv» rolu YAZILMIR — sətir tamamilə gizlənir.
    admin_position_label = resolve_position_label(
        title=getattr(admin_membership, "title", "") or "",
        staff_position=(profile.staff_position or ""),
        role_name=getattr(getattr(admin_membership, "role", None), "name", "") or "",
        role_label=getattr(getattr(admin_membership, "role", None), "display_name", "") or "",
    )

    context = {
        "profile_user": profile_user,
        "profile": profile,
        "display_name": display_name,
        "profile_bio": (profile.bio or "").strip(),
        "profile_location": (profile.location or "").strip(),
        "admin_membership": admin_membership,
        "admin_position_label": admin_position_label,
        "academic_display_groups": academic_profile.display_groups_for(profile_user),
        "contact_phones": contact_phones,
        "is_self_preview": is_self_preview,
        **posts_result["context"],
    }
    return render(request, "accounts/public_profile.html", context)
