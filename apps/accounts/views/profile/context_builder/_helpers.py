"""build_profile_response — kiçik köməkçilər."""

from django.utils.translation import gettext as _

from core.tenancy import restore_request_organization_from_profile

from ....models import ProfileRole
from ..._helpers import PROFILE_ROLE_LABELS
from ..constants import PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK, PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT


def _build_effective_user_roles(user, profile):
    role_names = []

    if getattr(user, "is_superuser", False):
        role_names.append(ProfileRole.SUPERADMIN)

    if hasattr(user, "get_all_roles"):
        for role_name in user.get_all_roles():
            normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
            if normalized_role_name in PROFILE_ROLE_LABELS and normalized_role_name not in role_names:
                role_names.append(normalized_role_name)

    fallback_role_name = ProfileRole.normalize_membership_role_name(getattr(profile, "role", ""))
    if fallback_role_name in PROFILE_ROLE_LABELS and fallback_role_name not in role_names:
        role_names.append(fallback_role_name)

    role_names.sort(key=lambda role_name: (ProfileRole.LEVELS.get(role_name, 0), role_name), reverse=True)
    return [
        {
            "name": role_name,
            "label": PROFILE_ROLE_LABELS.get(role_name, role_name.replace("_", " ").title()),
        }
        for role_name in role_names
    ]


def _restore_profile_org_context(request, profile, active_section):
    """
    Re-hydrate the active organization for org-bound profile sections when the
    session lost its tenant selection but the profile still points at a valid org.
    """
    if active_section not in PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT:
        return
    restore_request_organization_from_profile(
        request,
        profile=profile,
        allow_multi_org_restore=active_section in PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK,
    )


def _get_publish_notification_targets(user, capabilities):
    """Return list of target options for notification publishing based on role."""
    from apps.exams.models import StudentGroup
    from apps.organizations.models import Membership

    targets = []
    is_superadmin = capabilities["is_superadmin"]
    is_org_admin = capabilities["is_org_admin"]
    is_teacher = capabilities["is_teacher"]

    if is_superadmin:
        # "All users" is exclusive — if selected, ignore specific org selections
        targets.append(
            {
                "value": "all",
                "label": _("target_all_users"),
                "is_exclusive": True,
            }
        )
        from apps.organizations.models import Organization

        # QEYD: tərcümə çağırışları f-string İÇİNDƏ OLMAMALIDIR — xgettext
        # (makemessages) onları görmür və tərcümələri obsolete edir.
        org_prefix_label = _("target_org_prefix")
        for org in Organization.objects.filter(is_active=True, status="active").order_by("name"):
            targets.append(
                {
                    "value": f"org_{org.pk}",
                    "label": f"{org_prefix_label}: {org.name}",
                    "is_exclusive": False,
                }
            )
        return targets

    # Non-superadmin targets are cumulative: a user can be both an organization
    # admin (e.g. an owner) and a teacher, in which case they should be able to
    # target the whole organization as well as their own student groups.
    if is_org_admin:
        # Get user's active org memberships
        org_memberships = (
            Membership.objects.filter(user=user, is_active=True, organization__is_active=True)
            .select_related("organization")
            .order_by("organization__name", "organization_id", "-role__level", "id")
        )
        seen_org_ids = set()
        org_prefix_label = _("target_org_prefix")
        all_members_label = _("target_org_all_members")
        for membership in org_memberships:
            if membership.organization_id in seen_org_ids:
                continue
            seen_org_ids.add(membership.organization_id)
            targets.append(
                {
                    "value": f"org_{membership.organization_id}",
                    "label": f"{org_prefix_label}: {membership.organization.name} ({all_members_label})",
                    "is_exclusive": False,
                }
            )

    if is_teacher:
        teacher_groups = StudentGroup.objects.filter(teacher=user).order_by("name")
        group_prefix_label = _("target_group_prefix")
        for group in teacher_groups:
            targets.append(
                {
                    "value": f"group_{group.pk}",
                    "label": f"{group_prefix_label}: {group.name}",
                    "is_exclusive": False,
                }
            )
    return targets
