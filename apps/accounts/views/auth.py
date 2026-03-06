"""
Authentication views: registration, verification, login, logout.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.views import LoginView
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType

from ..forms import CustomLoginForm, RegisterForm
from ..models import ProfileRole, UserProfile
from ._helpers import (
    _activate_verified_student_membership,
    _get_signup_lookup_payload,
    _map_signup_role_to_profile_role,
    _resolve_membership_role,
    signer,
)

User = get_user_model()


class CustomLoginView(LoginView):
    """Login view with custom form and suspended-organization checks."""

    template_name = "accounts/login.html"
    authentication_form = CustomLoginForm
    redirect_authenticated_user = True


def register_view(request):
    """User registration with organization bootstrap and email verification."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            from apps.organizations.models import Country, Membership, Organization, Role

            with transaction.atomic():
                user = form.save(commit=False)
                user.email = form.cleaned_data["email"]
                user.set_password(form.cleaned_data["password"])
                # Account becomes active only after OTP/email-link verification.
                user.is_active = False
                user.save()

                signup_mode = form.cleaned_data.get("signup_mode", "individual")
                organization_type = form.cleaned_data["organization_type"]
                country_code = form.cleaned_data.get("country", "")
                country_obj = Country.objects.filter(code=country_code).first()
                country_name = country_obj.name if country_obj else country_code
                join_organization = form.cleaned_data.get("join_organization")
                institution_not_listed_name = form.cleaned_data.get("institution_not_listed_name", "")
                organization_identifier = form.cleaned_data.get("organization_identifier", "")
                organization_license_identifier = form.cleaned_data.get("organization_license_identifier", "")
                initial_role = form.cleaned_data.get("initial_role", ProfileRole.MEMBER)

                organization = None
                requested_organization = None
                requested_organization_name = ""
                resolved_identifier = organization_identifier

                if signup_mode == "individual":
                    owner_display_name = (f"{user.first_name} {user.last_name}").strip() or user.username
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
                profile.role = _map_signup_role_to_profile_role(initial_role)
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
                profile.student_school_identifier = (
                    resolved_identifier if organization_type == OrganizationType.SCHOOL else ""
                )
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

                    request.session["active_organization"] = organization.slug

            EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)
            code = generate_otp()
            EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timedelta(minutes=10))
            send_verify_email(user, code)
            request.session["pending_verify_email"] = user.email

            if organization is None and requested_organization_name:
                messages.success(
                    request,
                    pgettext_lazy("accounts.auth.message", "registration_completed_request_recorded"),
                )
            else:
                messages.success(
                    request,
                    pgettext_lazy("accounts.auth.message", "registration_completed_you_can_login_now"),
                )
            messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
            return redirect("accounts:verify_code")
    else:
        form = RegisterForm()

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "lookup_payload": _get_signup_lookup_payload(),
        },
    )


def verify_code_view(request):
    """Verify email using OTP code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext_lazy("accounts.auth.message", "verification_email_not_found_register_again"))
        return redirect("accounts:register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
            return redirect("accounts:register")

        otp = EmailOTP.objects.filter(user=user, code=code, is_used=False).order_by("-created_at").first()
        if not otp or otp.is_expired():
            messages.error(request, pgettext_lazy("accounts.auth.message", "code_invalid_or_expired"))
            return render(request, "accounts/verify_code.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()
        joined_organization = _activate_verified_student_membership(user)
        if joined_organization is not None:
            request.session["active_organization"] = joined_organization.slug
        request.session.pop("pending_verify_email", None)

        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")

    return render(request, "accounts/verify_code.html", {"email": email})


def verify_email_link_view(request):
    """Verify email using signed token link."""
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=60 * 10)  # 10 minutes
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        joined_organization = _activate_verified_student_membership(user)
        if joined_organization is not None:
            request.session["active_organization"] = joined_organization.slug
        request.session.pop("pending_verify_email", None)
        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, pgettext_lazy("accounts.auth.message", "link_invalid_or_expired"))
        return redirect("accounts:register")


def resend_code_view(request):
    """Resend email verification code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext_lazy("accounts.auth.message", "email_not_found"))
        return redirect("accounts:register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
        return redirect("accounts:register")
    if user.is_active:
        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")

    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)
    code = generate_otp()
    EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timedelta(minutes=10))
    send_verify_email(user, code)

    messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
    return redirect("accounts:verify_code")


def logout_view(request):
    """Logout user and redirect to home."""
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
    return redirect("home")
