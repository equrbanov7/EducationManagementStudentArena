"""
User organization access rows builder.

Builds the list of organizations a user can access (via membership, ownership,
or superadmin context) for the profile "organizations" panel.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count
from django.urls import reverse

from core.staff_position import visible_role_label

from ...models import ProfileRole
from .constants import PROFILE_ROLE_LABELS
from .formatting import _append_query_params
from .rbac import _is_superadmin_user

User = get_user_model()

#: Kartın keçid açarı → kabinet bölməsi (aktiv təşkilat üçün, bölmə icazəlidirsə).
_CABINET_LINKS = (
    ("dashboard_url", "org-overview"),
    ("members_url", "org-members"),
    ("roles_url", "org-roles"),
)


#: Təşkilat kartındakı üzv sayı — 5 dəqiqəlik keş (tutum testi 2026-10-05: hər kabinet
#: açılışı 50 000 üzvlü təşkilatda COUNT ~80 ms, pikdə 2 s; 500 tələbədə DB doyurdu).
_MEMBER_COUNT_CACHE_SECONDS = 300


def _cached_member_counts(org_ids):
    if not org_ids:
        return {}
    keys = {org_id: f"emsarena:org-member-count:{org_id}" for org_id in org_ids}
    try:
        cached = cache.get_many(list(keys.values()))
    except Exception:
        cached = {}
    counts = {org_id: cached[key] for org_id, key in keys.items() if key in cached}
    missing = [org_id for org_id in org_ids if org_id not in counts]
    if missing:
        from apps.organizations.models import Membership

        fresh = {
            row["organization_id"]: row["member_count"]
            for row in Membership.objects.filter(organization_id__in=missing, is_active=True)
            .values("organization_id")
            .annotate(member_count=Count("id"))
        }
        fresh = {org_id: fresh.get(org_id, 0) for org_id in missing}
        counts.update(fresh)
        try:
            cache.set_many({keys[org_id]: value for org_id, value in fresh.items()}, _MEMBER_COUNT_CACHE_SECONDS)
        except Exception:
            pass
    return counts


def _build_user_organization_access_rows(
    user,
    *,
    active_organization=None,
    include_active_superadmin_org=False,
    profile_section="profile-info",
    allowed_sections=None,
):
    """Profil kartı «Təşkilat girişləri»nin sətirləri.

    ``allowed_sections`` (aktorun kabinet bölmələri) verilibsə, AKTİV təşkilatın
    «Panel / Üzvlər / Rollar» keçidləri kabinet bölmələrinə aparır (sahib
    2026-10-01: «bir səhifə, bir URL»). Bölmə açıq deyilsə və ya sətir başqa
    təşkilatdırsa köhnə ``/organizations/<slug>/…`` URL-i qalır — o da artıq
    eyni qapı ilə kabinetə yönləndirir (``organizations.cabinet_links``).
    """
    from apps.organizations.models import Membership, Organization

    if not user or not getattr(user, "is_authenticated", False):
        return []

    membership_queryset = (
        Membership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "organization__owner", "role")
        .order_by("organization__name", "-is_primary", "-role__level", "role__display_name")
    )

    grouped_rows = {}
    for membership in membership_queryset:
        organization = membership.organization
        row = grouped_rows.setdefault(
            organization.id,
            {
                "organization": organization,
                "memberships": [],
                "role_labels": [],
                "access_origin": "membership",
                "is_owner": organization.owner_id == user.id,
            },
        )
        row["memberships"].append(membership)
        # ⚠️ Doldurucu «Üzv» rolu nişan kimi göstərilmir — sətir nişansız qalır.
        role_label = visible_role_label(membership.role.name, membership.role.display_name)
        if role_label and role_label not in row["role_labels"]:
            row["role_labels"].append(role_label)

    owned_organizations = (
        Organization.objects.filter(owner=user, is_active=True, status="active")
        .select_related("owner")
        .order_by("name")
    )
    for organization in owned_organizations:
        row = grouped_rows.setdefault(
            organization.id,
            {
                "organization": organization,
                "memberships": [],
                "role_labels": [],
                "access_origin": "owner",
                "is_owner": True,
            },
        )
        row["is_owner"] = True
        if PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER] not in row["role_labels"]:
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER])
        if row["access_origin"] != "membership":
            row["access_origin"] = "owner"

    if (
        include_active_superadmin_org
        and _is_superadmin_user(user)
        and active_organization is not None
        and getattr(active_organization, "is_active", False)
        and getattr(active_organization, "status", "") == "active"
        and active_organization.id not in grouped_rows
    ):
        grouped_rows[active_organization.id] = {
            "organization": active_organization,
            "memberships": [],
            "role_labels": [PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN]],
            "access_origin": "superadmin",
            "is_owner": active_organization.owner_id == user.id,
        }

    org_ids = list(grouped_rows.keys())
    member_counts = _cached_member_counts(org_ids)

    profile_url = reverse("accounts:profile")
    section_url = _append_query_params(profile_url, section=profile_section)
    cabinet_sections = set(allowed_sections or ())
    rows = []
    for row in grouped_rows.values():
        organization = row["organization"]
        if (
            row["access_origin"] == "superadmin"
            and PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN] not in row["role_labels"]
        ):
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN])
        if row["is_owner"] and PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER] not in row["role_labels"]:
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER])

        row["is_current"] = active_organization is not None and organization.id == active_organization.id
        row["member_count"] = member_counts.get(organization.id, 0)
        row["status_label"] = (
            "Aktiv"
            if organization.is_active and organization.status == "active"
            else ("Dayandırılıb" if organization.is_suspended else "Qeyri-aktiv")
        )
        row["switch_url"] = _append_query_params(
            reverse("organizations:switch", kwargs={"slug": organization.slug}),
            next=section_url,
        )
        row["dashboard_url"] = reverse("organizations:dashboard", kwargs={"slug": organization.slug})
        row["members_url"] = reverse("organizations:members", kwargs={"slug": organization.slug})
        row["roles_url"] = reverse("organizations:roles", kwargs={"slug": organization.slug})
        row["settings_url"] = reverse("organizations:settings", kwargs={"slug": organization.slug})
        if row["is_current"]:
            for key, section in _CABINET_LINKS:
                if section in cabinet_sections:
                    row[key] = _append_query_params(profile_url, section=section)
        rows.append(row)

    rows.sort(
        key=lambda item: (
            not item["is_current"],
            item["organization"].name.lower(),
        )
    )
    return rows
