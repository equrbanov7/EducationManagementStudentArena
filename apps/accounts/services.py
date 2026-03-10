"""
Business logic layer for accounts app.
This module contains service functions that encapsulate business operations.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam
from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType
from core.utils import get_auth_otp_expiry_minutes, get_auth_otp_expiry_seconds

from .models import ProfileRole, UserProfile

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Role Management Services
# ════════════════════════════════════════════════════════════════════════════


def is_superadmin_user(user):
    """Check if user is a superadmin."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (user.is_superuser or getattr(user, "is_superadmin", False))
    )


def get_user_role_level(user):
    """Get numeric role level for user."""
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    if is_superadmin_user(user):
        return 999
    if hasattr(user, "_highest_role_level"):
        return int(user._highest_role_level())

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", "")
    return int(ProfileRole.LEVELS.get(profile_role, 0))


def user_has_any_role(user, role_names):
    """Check if user has any of the specified roles."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    normalized = set(role_names or [])
    if not normalized:
        return False
    if hasattr(user, "has_role"):
        return any(user.has_role(role_name) for role_name in normalized)

    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None) in normalized


def get_profile_role_label(role):
    """Get display label for profile role."""
    return dict(ProfileRole.CHOICES).get(role, role)


def map_signup_role_to_profile_role(initial_role):
    """Map signup role to profile role."""
    role_mapping = {
        ProfileRole.STUDENT: ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT: ProfileRole.LEAD_STUDENT,
        ProfileRole.TEACHER: ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER: ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.ADMIN: ProfileRole.ADMIN,
        ProfileRole.HR: ProfileRole.HR,
        ProfileRole.MEMBER: ProfileRole.MEMBER,
    }
    return role_mapping.get(initial_role, ProfileRole.MEMBER)


# ════════════════════════════════════════════════════════════════════════════
# User Registration Services
# ════════════════════════════════════════════════════════════════════════════


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
    """
    Create a new user with organization setup.

    Args:
        username: Username for the new user
        email: Email address
        password: Plain password (will be hashed)
        first_name: User's first name
        last_name: User's last name
        signup_mode: One of 'individual', 'organization_create', 'student_join'
        organization_type: Type of organization
        country_code: Country code
        country_name: Full country name
        join_organization: Organization to join (for student_join mode)
        institution_not_listed_name: Name for new organization
        organization_identifier: Organization identifier
        organization_license_identifier: License identifier
        initial_role: Initial profile role

    Returns:
        tuple: (user, organization, requested_organization, profile)
    """
    from apps.organizations.models import Membership, Organization, Role

    # Create user account (inactive until verified)
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

    # Handle organization creation based on signup mode
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
    else:  # student_join
        requested_organization = join_organization
        requested_organization_name = join_organization.name if join_organization else ""
        resolved_identifier = (
            join_organization.organization_identifier if join_organization else organization_identifier
        )

    # Create user profile
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

    # Create student organization request if needed
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

    # Create organization membership
    if organization is not None:
        from ._helpers import _resolve_membership_role

        membership_role = _resolve_membership_role(organization, initial_role)
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


# ════════════════════════════════════════════════════════════════════════════
# OTP and Email Verification Services
# ════════════════════════════════════════════════════════════════════════════


def send_verification_otp(user, *, request=None):
    """
    Generate and send OTP code to user's email.

    Args:
        user: User instance

    Returns:
        str: Generated OTP code
    """
    code, expires_at = issue_email_otp(user)
    send_verify_email(user, code, request=request, expires_at=expires_at)
    return code


def issue_email_otp(user):
    """
    Create a fresh OTP for a user and invalidate older pending OTPs.
    """
    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    code = generate_otp()
    expires_at = timezone.now() + timedelta(seconds=get_auth_otp_expiry_seconds())
    EmailOTP.objects.create(user=user, code=code, expires_at=expires_at)
    return code, expires_at


def get_latest_pending_otp(user):
    """
    Return the newest unused OTP for a user, even if it has already expired.
    """
    if not user:
        return None
    return EmailOTP.objects.filter(user=user, is_used=False).order_by("-created_at").first()


def get_otp_timer_context(user):
    """
    Build timer metadata for OTP-related templates.
    """
    otp = get_latest_pending_otp(user)
    return {
        "otp_expires_at": getattr(otp, "expires_at", None),
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "otp_expiry_seconds": get_auth_otp_expiry_seconds(),
    }


def verify_otp_code(user, code):
    """
    Verify OTP code for user.

    Args:
        user: User instance
        code: OTP code string

    Returns:
        tuple: (success: bool, otp: EmailOTP or None)
    """
    otp = EmailOTP.get_matching_otp(user=user, code=code)

    if not otp or otp.is_expired():
        return False, None

    return True, otp


def activate_user_account(user):
    """
    Activate user account and mark OTP as used.

    Args:
        user: User instance
        otp: EmailOTP instance (optional)

    Returns:
        Organization or None: Organization user joined (if student)
    """
    from ._helpers import _activate_verified_student_membership

    user.is_active = True
    user.save()

    joined_organization = _activate_verified_student_membership(user)
    return joined_organization


# ════════════════════════════════════════════════════════════════════════════
# Profile Update Services
# ════════════════════════════════════════════════════════════════════════════


def update_user_profile(user, **kwargs):
    """
    Update user profile fields.

    Args:
        user: User instance
        **kwargs: Profile fields to update

    Returns:
        UserProfile: Updated profile instance
    """
    profile = user.profile

    # Update allowed fields
    allowed_fields = [
        'bio', 'location', 'website', 'phone', 'birthday',
        'linkedin_url', 'github_url', 'twitter_url',
        'student_id', 'student_university_name', 'student_school_identifier',
        'avatar'
    ]

    for field in allowed_fields:
        if field in kwargs:
            setattr(profile, field, kwargs[field])

    profile.save()
    return profile


def update_user_role(user, new_role, updated_by):
    """
    Update user's profile role.

    Args:
        user: User instance
        new_role: New role string
        updated_by: User making the change

    Returns:
        UserProfile: Updated profile
    """
    profile = user.profile
    profile.role = new_role
    profile.save()

    return profile


# ════════════════════════════════════════════════════════════════════════════
# Query Helper Services
# ════════════════════════════════════════════════════════════════════════════


def get_assigned_courses_for_user(user, organization=None):
    """
    Get courses assigned to user as student.

    Args:
        user: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Course queryset
    """
    qs = Course.objects.filter(
        memberships__user=user,
        memberships__role="student",
        status="published",
    ).distinct()

    if organization is not None:
        qs = qs.filter(organization=organization)

    return qs.select_related("owner").order_by("-created_at")


def get_assigned_exams_for_user(user, organization=None, active_only=True):
    """
    Get exams assigned to user.

    Args:
        user: User instance
        organization: Optional organization filter
        active_only: Filter to active exams only

    Returns:
        QuerySet: Exam queryset
    """
    assignment_filter = (
        Q(allowed_users=user)
        | Q(allowed_groups__students=user)
        | Q(
            course__memberships__user=user,
            course__memberships__role="student",
            course__status="published",
        )
    )

    qs = Exam.objects.filter(assignment_filter).distinct()

    if active_only:
        qs = qs.filter(is_active=True)

    if organization is not None:
        qs = qs.filter(organization=organization)

    return qs.select_related("author", "course").order_by("-created_at")


def get_course_membership_groups(user, course_ids):
    """
    Get group names for user's course memberships.

    Args:
        user: User instance
        course_ids: List of course IDs

    Returns:
        dict: {course_id: set(group_names)}
    """
    memberships = CourseMembership.objects.filter(
        course_id__in=course_ids,
        user=user,
        role="student",
    ).values_list("course_id", "group_name")

    course_groups = {}
    for course_id, group_name in memberships:
        normalized_group = (group_name or "").strip().lower()
        if not normalized_group:
            continue
        course_groups.setdefault(course_id, set()).add(normalized_group)

    return course_groups


# ════════════════════════════════════════════════════════════════════════════
# Score Parsing Services
# ════════════════════════════════════════════════════════════════════════════


def parse_decimal_score(value, *, default=None):
    """
    Parse a score value to Decimal.

    Args:
        value: Value to parse (string, int, float, Decimal)
        default: Default value if parsing fails

    Returns:
        Decimal or default
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return default
