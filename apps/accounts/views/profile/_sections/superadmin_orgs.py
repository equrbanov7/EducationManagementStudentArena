"""Profil "superadmin-org-features" / "superadmin-organizations" bölmələri.

`features_section` və `organizations_section` dict-lərini YERİNDƏ mutasiya edir
(köhnə inline blokla eyni akkumulyator davranışı).
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

from apps.accounts.views._helpers.formatting import _append_query_params, _query_string


def build_superadmin_orgs_sections(
    request,
    features_section,
    organizations_section,
    *,
    allowed_sections,
    active_section,
    organization_access_rows,
):
    from apps.organizations.models import REVIEW_VISIBILITY_FEATURES, Organization

    superadmin_organizations_queryset = (
        Organization.objects.select_related("owner")
        .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
        .order_by("name")
    )
    organization_status_filter = (request.GET.get("status") or "").strip().lower()
    if organization_status_filter in {"active", "pending", "suspended"}:
        superadmin_organizations_queryset = superadmin_organizations_queryset.filter(status=organization_status_filter)
    elif organization_status_filter == "inactive":
        superadmin_organizations_queryset = superadmin_organizations_queryset.filter(is_active=False).exclude(
            status="suspended"
        )

    if "superadmin-org-features" in allowed_sections and active_section == "superadmin-org-features":
        superadmin_feature_org_page = request.GET.get("superadmin_feature_org_page")
        superadmin_org_features_page = Paginator(superadmin_organizations_queryset, 12).get_page(
            superadmin_feature_org_page
        )
        from apps.organizations.cabinet_modules import module_items as _cabinet_module_items

        for organization in superadmin_org_features_page.object_list:
            organization.cabinet_module_items = _cabinet_module_items(organization)
            organization.review_feature_items = [
                {
                    "key": feature_name,
                    "label": feature_config["label"],
                    "short_label": feature_config["short_label"],
                    "enabled": organization.is_review_identity_reveal_enabled(feature_name),
                }
                for feature_name, feature_config in REVIEW_VISIBILITY_FEATURES.items()
            ]
        features_section["organizations"] = superadmin_org_features_page
        features_section["organizations_pagination_query"] = _query_string(section="superadmin-org-features")
        features_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-org-features",
            superadmin_feature_org_page=superadmin_feature_org_page,
        )

    if "superadmin-organizations" in allowed_sections and active_section == "superadmin-organizations":
        superadmin_org_page = request.GET.get("superadmin_org_page")
        organizations_section["organizations"] = Paginator(superadmin_organizations_queryset, 12).get_page(
            superadmin_org_page
        )
        organizations_section["organization_access_rows"] = organization_access_rows
        organizations_section["all_modules"] = [
            "accounts",
            "organizations",
            "courses",
            "exams",
            "assignments",
            "projects",
            "labs",
            "live_exam",
            "blog",
            "audit",
        ]
        organizations_section["organizations_pagination_query"] = _query_string(section="superadmin-organizations")
        organizations_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-organizations",
            superadmin_org_page=superadmin_org_page,
        )
        organizations_section["pending_count"] = Organization.objects.filter(status="pending").count()
