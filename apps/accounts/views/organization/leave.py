"""
Leave organization view.

Lets eligible non-admin members leave their current organization with a
mandatory reason. Behavior is identical to the pre-refactor implementation.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse

from core.constants import OrganizationType

from ...models import ProfileRole, UserProfile
from .._helpers import _map_org_role_to_profile_role, _resolve_next_url

User = get_user_model()


@login_required
def student_leave_organization(request):
    """Allow eligible non-admin members to leave their current organization with mandatory reason."""
    from apps.organizations.models import Membership
    from apps.organizations.services import create_audit_log

    if request.method != "POST":
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    reason = (request.POST.get("leave_reason") or "").strip()
    back_url = _resolve_next_url(request, f"{reverse('accounts:profile')}?section=profile-info")
    if not reason:
        messages.error(request, "Təşkilatdan çıxmaq üçün səbəb qeyd etmək məcburidir.")
        return redirect(back_url)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    organization = profile.organization
    if organization is None:
        messages.error(request, "Hazırda bağlı olduğunuz təşkilat yoxdur.")
        return redirect(back_url)

    active_membership = (
        Membership.objects.filter(
            user=request.user,
            organization=organization,
            is_active=True,
        )
        .select_related("role")
        .order_by("-is_primary", "-role__level")
        .first()
    )
    membership_profile_role = _map_org_role_to_profile_role(getattr(active_membership, "role", None))
    can_leave_org = bool(
        getattr(organization, "owner_id", None) != request.user.id
        and (
            membership_profile_role
            in {
                ProfileRole.STUDENT,
                ProfileRole.LEAD_STUDENT,
                ProfileRole.TEACHER,
                ProfileRole.ASSISTANT_TEACHER,
                ProfileRole.MEMBER,
                ProfileRole.HR,
            }
            or (
                active_membership is None
                and profile.role
                in {
                    ProfileRole.STUDENT,
                    ProfileRole.LEAD_STUDENT,
                    ProfileRole.TEACHER,
                    ProfileRole.ASSISTANT_TEACHER,
                    ProfileRole.MEMBER,
                    ProfileRole.HR,
                }
            )
        )
    )
    if not can_leave_org:
        messages.error(request, "Bu əməliyyat yalnız tələbə, müəllim və staff hesabları üçün aktivdir.")
        return redirect(back_url)

    with transaction.atomic():
        Membership.objects.filter(user=request.user, organization=organization, is_active=True).update(
            is_active=False,
            is_primary=False,
        )
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.requested_organization = None
        profile.requested_organization_name = ""
        profile.requested_organization_message = ""
        profile.student_university_name = ""
        profile.student_school_identifier = ""
        profile.save(
            update_fields=[
                "organization",
                "organization_type",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "student_university_name",
                "student_school_identifier",
                "updated_at",
            ]
        )

    request.session.pop("active_organization", None)
    create_audit_log(
        user=request.user,
        organization=organization,
        action="update",
        resource_type="membership",
        resource_id=request.user.id,
        resource_repr=f"{request.user.username} left organization",
        old_values={"organization": organization.name},
        new_values={"organization": ""},
        reason=reason,
        request=request,
    )
    messages.success(request, f"{organization.name} təşkilatından ayrıldınız.")
    return redirect(back_url)
