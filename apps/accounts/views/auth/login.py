"""accounts auth view paketi — login."""

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.urls import reverse, reverse_lazy
from django.utils.translation import pgettext
from django.views.generic.edit import FormView

from apps.accounts.models import EmailOTP
from core.rate_limit import clear_rate_limit, is_rate_limited, normalize_rate_identity, record_rate_limit_hit
from core.utils import get_auth_otp_expiry_minutes, get_client_ip

from ...forms import CustomLoginForm, CustomPasswordResetForm, OTPPasswordResetCodeForm, OTPPasswordResetConfirmForm
from ...middleware import POST_LOGIN_REDIRECT_GUARD_SESSION_KEY
from ...services import get_otp_timer_context
from ._shared import (
    _authenticate_superadmin_for_rate_limit_reset,
    _clear_login_rate_limits_after_password_reset,
    _ensure_auth_device_cookie,
    _get_auth_device_id,
    _login_limit_keys,
    _sanitize_auth_redirect_target,
)
from .constants import (
    AUTH_RATE_LIMIT_MESSAGE,
    PASSWORD_RESET_EMAIL_SESSION_KEY,
    logger,
)

LOGIN_AUDIENCE_STUDENT = "student"
LOGIN_AUDIENCE_STAFF = "staff"


def _normalized_path(value):
    path = urlsplit(str(value or "")).path or "/"
    return f"{path.rstrip('/')}/"


class CustomLoginView(LoginView):
    """Login view with custom form and suspended-organization checks."""

    template_name = "accounts/login.html"
    authentication_form = CustomLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        """Inject brand-aware SEO metadata (no hard-coded product name).

        The login page is indexable and carries brand keywords; the title/
        description are built from the configured ``SITE_BRAND_NAME`` so the
        rebrand (Qərbi Kaspi Universiteti) flows through automatically.
        """
        context = super().get_context_data(**kwargs)
        brand = getattr(settings, "SITE_BRAND_NAME", "")
        next_url = context.get(self.redirect_field_name, "")
        student_cabinet_url = reverse("accounts:student_cabinet")
        staff_cabinet_url = reverse("accounts:staff_cabinet")
        audience = self._resolve_login_audience(next_url, student_cabinet_url, staff_cabinet_url)
        context.setdefault("seo_title", f"Daxil ol | {brand}".strip(" |"))
        context.setdefault(
            "seo_description",
            f"{brand} hesabınıza daxil olun və kabinet, imtahan, kurs və "
            "idarəetmə bölmələrindən istifadə edin.".strip(),
        )
        context.update(
            {
                "login_audience": audience,
                "login_portal_message": self._audience_message(audience),
            }
        )
        return context

    def _resolve_login_audience(self, next_url, student_cabinet_url, staff_cabinet_url):
        next_path = _normalized_path(next_url)
        student_paths = {
            _normalized_path(student_cabinet_url),
            _normalized_path(reverse("accounts:student_dashboard")),
        }
        staff_paths = {
            _normalized_path(staff_cabinet_url),
            _normalized_path(reverse("accounts:teacher_dashboard")),
            _normalized_path(reverse("accounts:cabinet")),
            _normalized_path(reverse("accounts:dashboard")),
        }
        if next_path in student_paths:
            return LOGIN_AUDIENCE_STUDENT
        if next_path in staff_paths:
            return LOGIN_AUDIENCE_STAFF
        return LOGIN_AUDIENCE_STAFF

    def _audience_message(self, audience):
        if audience == LOGIN_AUDIENCE_STUDENT:
            return pgettext(
                "accounts.login.audience",
                "Tələbə kabinetinə daxil olmaq üçün universitet hesabınızla giriş edin.",
            )
        return pgettext(
            "accounts.login.audience",
            "Müəllim və əməkdaş kabinetinə daxil olmaq üçün universitet hesabınızla giriş edin.",
        )

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return _ensure_auth_device_cookie(request, response)

    def get_redirect_url(self):
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name),
        )
        return _sanitize_auth_redirect_target(self.request, redirect_to)

    # No ``get_success_url`` override: with no safe ``next``, login falls back to
    # ``LOGIN_REDIRECT_URL`` = the canonical ``/kabinet/`` entry, which then
    # role-routes on that follow-up request (where the org role context is bound)
    # — teaching staff → teacher cabinet, everyone else → the unified profile
    # cabinet. Resolving the role here (mid-login-POST) is unreliable because the
    # active-organization context is bound for the *previously anonymous* request.

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        limit_keys = _login_limit_keys(request, username)

        for scope, *key_parts in limit_keys:
            is_limited, retry_after = is_rate_limited(scope, settings.LOGIN_RATE_LIMIT, *key_parts)
            if is_limited:
                superadmin_user = _authenticate_superadmin_for_rate_limit_reset(request, username, password)
                if superadmin_user is not None:
                    for reset_scope, *reset_key_parts in limit_keys:
                        clear_rate_limit(reset_scope, *reset_key_parts)
                    form.user_cache = superadmin_user
                    logger.warning(
                        "Cleared login rate limit after successful superadmin authentication",
                        extra={
                            "username": normalize_rate_identity(username),
                            "auth_device": _get_auth_device_id(request),
                            "client_ip": get_client_ip(request) or "unknown",
                        },
                    )
                    return self.form_valid(form)

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

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session[POST_LOGIN_REDIRECT_GUARD_SESSION_KEY] = True
        return response


class NamespacedPasswordResetView(PasswordResetView):
    """Password reset view that sends an OTP and keeps the reset on-site."""

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

    def form_valid(self, form):
        response = super().form_valid(form)
        reset_users = getattr(form, "password_reset_users", [])
        if reset_users:
            reset_email = EmailOTP.normalize_email(form.cleaned_data["email"])
            self.request.session[PASSWORD_RESET_EMAIL_SESSION_KEY] = reset_email
        else:
            self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return response


class NamespacedPasswordResetDoneView(FormView):
    template_name = "accounts/password_reset_done.html"
    form_class = OTPPasswordResetCodeForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_reset_email(self):
        return EmailOTP.normalize_email(self.request.session.get(PASSWORD_RESET_EMAIL_SESSION_KEY, ""))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["email"] = self.get_reset_email()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reset_email = self.get_reset_email()
        if reset_email:
            context.update(get_otp_timer_context(email=reset_email, purpose=EmailOTP.Purpose.PASSWORD_RESET))
        else:
            context["otp_expires_at"] = None
            context["otp_expiry_seconds"] = settings.AUTH_OTP_EXPIRY_SECONDS
        context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
        context["password_reset_email"] = reset_email
        return context

    def form_valid(self, form):
        user = form.save()
        _clear_login_rate_limits_after_password_reset(self.request, user)
        self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return super().form_valid(form)


class NamespacedPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view with namespaced completion redirect."""

    template_name = "accounts/password_reset_confirm.html"
    form_class = OTPPasswordResetConfirmForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if getattr(self, "user", None) is not None and getattr(self.user, "is_authenticated", False):
            context.update(get_otp_timer_context(self.user, purpose=EmailOTP.Purpose.PASSWORD_RESET))
        else:
            context["otp_expires_at"] = None
            context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
            context["otp_expiry_seconds"] = settings.AUTH_OTP_EXPIRY_SECONDS
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(form, "user", None) or getattr(self, "user", None)
        if user is not None:
            _clear_login_rate_limits_after_password_reset(self.request, user)
        self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return response
