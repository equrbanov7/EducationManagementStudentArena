"""
Authentication views: registration, verification, login, logout.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetDoneView, PasswordResetView
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import pgettext_lazy

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from core.constants import OrganizationType
from core.rate_limit import clear_rate_limit, is_rate_limited, normalize_rate_identity, record_rate_limit_hit
from core.utils import get_auth_otp_expiry_minutes
from core.utils import get_client_ip

from ..forms import CustomLoginForm, CustomPasswordResetForm, OTPPasswordResetConfirmForm, RegisterForm
from ..models import ProfileRole, UserProfile
from ..services import get_otp_timer_context, send_verification_otp, verify_otp_code
from apps.blog.models import EmailOTP
from ._helpers import (
    _activate_verified_student_membership,
    _get_signup_lookup_payload,
    _map_signup_role_to_profile_role,
    _resolve_membership_role,
    signer,
)

User = get_user_model()

AUTH_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."
LOGIN_LIMIT_SCOPE_IP = "accounts.login.ip"
LOGIN_LIMIT_SCOPE_IDENTITY = "accounts.login.identity"
OTP_VERIFY_LIMIT_SCOPE = "accounts.otp.verify"
OTP_RESEND_LIMIT_SCOPE = "accounts.otp.resend"


def _login_limit_keys(request, username):
    client_ip = get_client_ip(request) or "unknown"
    normalized_username = normalize_rate_identity(username)
    return [
        (LOGIN_LIMIT_SCOPE_IP, client_ip),
        (LOGIN_LIMIT_SCOPE_IDENTITY, client_ip, normalized_username),
    ]


def _otp_limit_key(request, email):
    return (
        get_client_ip(request) or "unknown",
        normalize_rate_identity(email),
    )


class CustomLoginView(LoginView):
    """Login view with custom form and suspended-organization checks."""

    template_name = "accounts/login.html"
    authentication_form = CustomLoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        username = request.POST.get("username", "")
        limit_keys = _login_limit_keys(request, username)

        for scope, *key_parts in limit_keys:
            is_limited, retry_after = is_rate_limited(scope, settings.LOGIN_RATE_LIMIT, *key_parts)
            if is_limited:
                form.add_error(None, AUTH_RATE_LIMIT_MESSAGE)
                response = self.render_to_response(self.get_context_data(form=form), status=429)
                if retry_after:
                    response.headers["Retry-After"] = str(retry_after)
                return response

        if form.is_valid():
            for scope, *key_parts in limit_keys:
                clear_rate_limit(scope, *key_parts)
            return self.form_valid(form)

        for scope, *key_parts in limit_keys:
            record_rate_limit_hit(scope, settings.LOGIN_RATE_LIMIT, *key_parts)
        return self.form_invalid(form)


class NamespacedPasswordResetView(PasswordResetView):
    """Password reset view that uses accounts namespace for redirects and email links."""

    template_name = "accounts/password_reset.html"
    form_class = CustomPasswordResetForm
    subject_template_name = "accounts/password_reset_subject.txt"
    email_template_name = "accounts/password_reset_email.txt"
    html_email_template_name = "accounts/password_reset_email.html"
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
        return context


class NamespacedPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
        return context


class NamespacedPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view with namespaced completion redirect."""

    template_name = "accounts/password_reset_confirm.html"
    form_class = OTPPasswordResetConfirmForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if getattr(self, "user", None) is not None and getattr(self.user, "is_authenticated", False):
            context.update(get_otp_timer_context(self.user))
        else:
            context["otp_expires_at"] = None
            context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
            context["otp_expiry_seconds"] = settings.AUTH_OTP_EXPIRY_SECONDS
        return context


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

            send_verification_otp(user, request=request)
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

        otp_limit_key = _otp_limit_key(request, email)
        is_limited, retry_after = is_rate_limited(
            OTP_VERIFY_LIMIT_SCOPE,
            settings.OTP_VERIFY_RATE_LIMIT,
            *otp_limit_key,
        )
        context = {
            "email": email,
            **get_otp_timer_context(user),
        }
        if is_limited:
            messages.error(request, AUTH_RATE_LIMIT_MESSAGE)
            response = render(request, "accounts/verify_code.html", context, status=429)
            if retry_after:
                response.headers["Retry-After"] = str(retry_after)
            return response

        _, otp = verify_otp_code(user, code)
        if not otp or otp.is_expired():
            record_rate_limit_hit(
                OTP_VERIFY_LIMIT_SCOPE,
                settings.OTP_VERIFY_RATE_LIMIT,
                *otp_limit_key,
            )
            messages.error(request, pgettext_lazy("accounts.auth.message", "code_invalid_or_expired"))
            return render(
                request,
                "accounts/verify_code.html",
                {
                    "email": email,
                    **get_otp_timer_context(user),
                },
            )

        otp.is_used = True
        otp.save()
        clear_rate_limit(OTP_VERIFY_LIMIT_SCOPE, *otp_limit_key)

        user.is_active = True
        user.save()
        joined_organization = _activate_verified_student_membership(user)
        if joined_organization is not None:
            request.session["active_organization"] = joined_organization.slug
        request.session.pop("pending_verify_email", None)

        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")

    user = User.objects.filter(email=email).first()
    return render(
        request,
        "accounts/verify_code.html",
        {
            "email": email,
            **get_otp_timer_context(user),
        },
    )


def verify_email_link_view(request):
    """Verify email using signed token link."""
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=settings.AUTH_OTP_EXPIRY_SECONDS)
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)
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

    otp_limit_key = _otp_limit_key(request, email)
    is_limited, retry_after = record_rate_limit_hit(
        OTP_RESEND_LIMIT_SCOPE,
        settings.OTP_RESEND_RATE_LIMIT,
        *otp_limit_key,
    )
    if is_limited:
        messages.error(request, AUTH_RATE_LIMIT_MESSAGE)
        response = render(request, "accounts/verify_code.html", {"email": email}, status=429)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    send_verification_otp(user, request=request)

    messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
    return redirect("accounts:verify_code")


def logout_view(request):
    """Logout user and redirect to home."""
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
    return redirect("home")
