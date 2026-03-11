"""
Registration and bootstrap services for accounts.
"""

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType

from ..models import ProfileRole, UserProfile
from ..policies import map_signup_role_to_profile_role, resolve_membership_role

User = get_user_model()


@transaction.atomic
def create_user_with_organization(
    username,
    email,
    password,
    first_name,
    last_name,
    signup_mode,
    organization_type,
    country_code,
    country_name,
    join_organization=None,
    institution_not_listed_name="",
    organization_identifier="",
    organization_license_identifier="",
    initial_role=ProfileRole.MEMBER,
):
    """Create a user, profile, request, and optional organization membership."""
    del country_code

    from apps.organizations.models import Membership, Organization, Role

    user = User.objects.create(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_active=False,
    )
    user.set_password(password)
    user.save()

    organization = None
    requested_organization = None
    requested_organization_name = ""
    resolved_identifier = organization_identifier

    if signup_mode == "individual":
        owner_display_name = (f"{first_name} {last_name}").strip() or username
        organization_name = f"{owner_display_name} Workspace"
        organization = Organization.objects.create(
            name=organization_name,
            org_type=OrganizationType.INDIVIDUAL,
            country=country_name,
            owner=user,
            status="active",
            is_active=True,
        )
        requested_organization = organization
        requested_organization_name = organization.name
    elif signup_mode == "organization_create":
        organization_name = institution_not_listed_name
        requested_organization_name = organization_name
        resolved_identifier = organization_identifier
        organization = Organization.objects.create(
            name=organization_name,
            org_type=organization_type,
            country=country_name,
            owner=user,
            status="active",
            is_active=True,
            organization_identifier=resolved_identifier,
            license_identifier=organization_license_identifier,
        )
        requested_organization = organization
        requested_organization_name = organization.name
    else:
        requested_organization = join_organization
        requested_organization_name = join_organization.name if join_organization else ""
        resolved_identifier = (
            join_organization.organization_identifier if join_organization else organization_identifier
        )

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.organization_type = organization.org_type if organization is not None else organization_type
    profile.organization = organization
    profile.requested_organization = requested_organization
    profile.requested_organization_name = requested_organization_name
    profile.requested_organization_message = ""
    profile.country = country_name
    profile.role = map_signup_role_to_profile_role(initial_role)
    profile.student_university_name = (
        requested_organization_name
        if signup_mode == "student_join"
        or organization_type
        in {
            OrganizationType.UNIVERSITY,
            OrganizationType.SCHOOL,
            OrganizationType.COURSE_CENTER,
        }
        else ""
    )
    profile.student_school_identifier = resolved_identifier if organization_type == OrganizationType.SCHOOL else ""
    profile.save()

    if (
        organization is None
        and requested_organization is not None
        and profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}
    ):
        StudentOrganizationRequest.objects.update_or_create(
            user=user,
            organization=requested_organization,
            status=StudentOrganizationRequestStatus.PENDING,
            defaults={
                "message": "",
                "resolution_note": "",
                "responded_by": None,
                "responded_at": None,
            },
        )

    if organization is not None:
        membership_role = resolve_membership_role(organization, initial_role)
        if membership_role is None:
            membership_role = Role.objects.create(
                organization=organization,
                name="owner",
                display_name="Owner",
                level=100,
                scope_type="organization",
                permissions=["*"],
                is_system=False,
                is_active=True,
            )

        Membership.objects.create(
            user=user,
            organization=organization,
            role=membership_role,
            is_primary=True,
            is_active=True,
            assigned_by=user,
        )

    return user, organization, requested_organization, profile


__all__ = ["create_user_with_organization"]
