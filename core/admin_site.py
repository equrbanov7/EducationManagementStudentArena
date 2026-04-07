"""
Custom Django AdminSite with enforced OTP verification for admin users.
"""

from __future__ import annotations

import logging

from django.contrib import admin, messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from apps.accounts.models import EmailOTP
from apps.accounts.services import verify_otp_code
from core.admin_auth import (
    AdminOTPForm,
    admin_2fa_pending_for_request,
    admin_2fa_required_for_user,
    admin_2fa_verified,
    admin_resend_rate_limited,
    admin_verify_rate_limited,
    clear_admin_2fa_state,
    clear_admin_verify_rate_limit,
    log_admin_security_event,
    mark_admin_2fa_pending,
    mark_admin_2fa_verified,
    pop_admin_2fa_next_url,
    record_admin_resend_hit,
    record_admin_verify_failure,
    send_admin_otp_email,
)
from core.constants import AuditAction
from core.utils import get_auth_otp_expiry_minutes

logger = logging.getLogger(__name__)


class EMSArenaAdminSite(admin.AdminSite):
    site_header = "EMS Arena Administration"
    site_title = "EMS Arena Admin"
    index_title = "Platform administration"

    def _begin_admin_otp_challenge(self, request, user, *, next_url: str):
        try:
            send_admin_otp_email(user, request=request)
        except Exception:
            logger.exception("Admin OTP delivery failed for user %s", user.pk)
            clear_admin_2fa_state(request)
            logout(request)
            messages.error(
                request,
                "Admin OTP email gonderile bilmedi. Zəhmət olmasa biraz sonra yenidən cəhd edin.",
            )
            log_admin_security_event(
                action=AuditAction.DENY,
                request=request,
                user=user,
                reason="Admin login blocked because OTP email delivery failed.",
                resource_type="admin_otp_delivery_failed",
                resource_id=str(user.pk),
            )
            return redirect(reverse("admin:login", current_app=self.name))

        mark_admin_2fa_pending(request, next_url=next_url)
        log_admin_security_event(
            action=AuditAction.CHALLENGE,
            request=request,
            user=user,
            reason="Admin password accepted and OTP challenge issued.",
            resource_type="admin_otp_challenge",
            resource_id=str(user.pk),
        )
        messages.info(request, "Admin giriş üçün OTP kodu email ünvanınıza göndərildi.")
        return redirect(reverse("admin:verify-otp", current_app=self.name))

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("verify-otp/", self.verify_otp_view, name="verify-otp"),
            path("resend-otp/", self.resend_otp_view, name="resend-otp"),
        ]
        return custom_urls + urls

    def has_permission(self, request):
        base_allowed = super().has_permission(request)
        if not base_allowed:
            return False
        return admin_2fa_verified(request)

    @method_decorator(never_cache)
    @method_decorator(login_not_required)
    def login(self, request, extra_context=None):
        user = getattr(request, "user", None)
        if admin_2fa_pending_for_request(request):
            request.current_app = self.name
            return redirect(reverse("admin:verify-otp", current_app=self.name))

        if request.method == "GET" and admin_2fa_required_for_user(user) and not admin_2fa_verified(request):
            next_url = request.GET.get("next") or reverse("admin:index", current_app=self.name)
            request.current_app = self.name
            return self._begin_admin_otp_challenge(request, user, next_url=next_url)

        response = super().login(request, extra_context=extra_context)

        if request.method != "POST":
            return response

        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            submitted_identity = str(request.POST.get("username", "")).strip()
            if submitted_identity:
                log_admin_security_event(
                    action=AuditAction.DENY,
                    request=request,
                    reason="Admin login failed because the submitted credentials were rejected.",
                    resource_type="admin_login_failed",
                    resource_id=submitted_identity,
                )
            return response

        if not admin_2fa_required_for_user(user):
            return response

        next_url = response.headers.get("Location", "")
        default_admin_url = reverse("admin:index", current_app=self.name)
        if not next_url or next_url == "/":
            next_url = default_admin_url
        request.current_app = self.name
        return self._begin_admin_otp_challenge(request, user, next_url=next_url)

    @method_decorator(never_cache)
    def verify_otp_view(self, request):
        request.current_app = self.name
        user = getattr(request, "user", None)
        if not admin_2fa_required_for_user(user):
            return redirect_to_login(request.get_full_path(), reverse("admin:login", current_app=self.name))

        if admin_2fa_verified(request):
            return redirect(pop_admin_2fa_next_url(request, reverse("admin:index", current_app=self.name)))

        if not admin_2fa_pending_for_request(request):
            mark_admin_2fa_pending(request, next_url=reverse("admin:index", current_app=self.name))
            try:
                send_admin_otp_email(user, request=request)
            except Exception:
                logger.exception("Admin OTP bootstrap delivery failed for user %s", user.pk)
                messages.error(request, "OTP kodu göndərilə bilmədi. Yenidən daxil olun.")
                return redirect(reverse("admin:login", current_app=self.name))

        form = AdminOTPForm(request.POST or None)
        retry_after = None

        if request.method == "POST":
            is_limited, retry_after = admin_verify_rate_limited(request, user=user)
            if is_limited:
                log_admin_security_event(
                    action=AuditAction.DENY,
                    request=request,
                    user=user,
                    reason="Admin OTP verification blocked by rate limiting.",
                    resource_type="admin_otp_verify_rate_limited",
                    resource_id=str(user.pk),
                )
                form.add_error(None, "Çox sayda yalnış OTP cəhdi edildi. Bir az sonra yenidən cəhd edin.")
            elif form.is_valid():
                success, otp = verify_otp_code(
                    user,
                    form.cleaned_data["code"],
                    purpose=EmailOTP.Purpose.ADMIN_LOGIN,
                )
                if not success or otp is None:
                    retry_limited, retry_after = record_admin_verify_failure(request, user=user)
                    log_admin_security_event(
                        action=AuditAction.DENY,
                        request=request,
                        user=user,
                        reason="Admin OTP verification failed because an invalid code was submitted.",
                        resource_type="admin_otp_failed",
                        resource_id=str(user.pk),
                    )
                    form.add_error("code", "OTP kodu yanlışdır və ya vaxtı bitib.")
                    if retry_limited:
                        form.add_error(None, "Çox sayda yalnış OTP cəhdi edildi. Bir az sonra yenidən cəhd edin.")
                else:
                    otp.is_used = True
                    otp.is_verified = True
                    otp.save(update_fields=["is_used", "is_verified"])
                    clear_admin_verify_rate_limit(request, user=user)
                    mark_admin_2fa_verified(request)
                    log_admin_security_event(
                        action=AuditAction.VERIFY,
                        request=request,
                        user=user,
                        reason="Admin OTP verification succeeded.",
                        resource_type="admin_otp_verified",
                        resource_id=str(user.pk),
                    )
                    messages.success(request, "Admin giriş təsdiqləndi.")
                    return redirect(pop_admin_2fa_next_url(request, reverse("admin:index", current_app=self.name)))

        context = {
            "site_header": self.site_header,
            "site_title": self.site_title,
            "title": "Admin OTP təsdiqi",
            "form": form,
            "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
            "resend_url": reverse("admin:resend-otp", current_app=self.name),
            "retry_after": retry_after,
        }
        response = TemplateResponse(request, "admin/verify_otp.html", context)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    @method_decorator(never_cache)
    def resend_otp_view(self, request):
        request.current_app = self.name
        user = getattr(request, "user", None)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        if not admin_2fa_required_for_user(user):
            return redirect(reverse("admin:login", current_app=self.name))

        is_limited, retry_after = admin_resend_rate_limited(request, user=user)
        if is_limited:
            log_admin_security_event(
                action=AuditAction.DENY,
                request=request,
                user=user,
                reason="Admin OTP resend blocked by rate limiting.",
                resource_type="admin_otp_resend_rate_limited",
                resource_id=str(user.pk),
            )
            messages.error(request, "OTP kodunu çox tez-tez yeniləyirsiniz. Bir az sonra yenidən cəhd edin.")
            response = redirect(reverse("admin:verify-otp", current_app=self.name))
            response.headers["Retry-After"] = str(retry_after or 60)
            return response

        record_admin_resend_hit(request, user=user)
        try:
            send_admin_otp_email(user, request=request)
        except Exception:
            logger.exception("Admin OTP resend failed for user %s", getattr(user, "pk", "<unknown>"))
            log_admin_security_event(
                action=AuditAction.DENY,
                request=request,
                user=user,
                reason="Admin OTP resend failed because email delivery raised an exception.",
                resource_type="admin_otp_resend_failed",
                resource_id=str(user.pk),
            )
            messages.error(request, "OTP kodu göndərilə bilmədi. Yenidən cəhd edin.")
            return redirect(reverse("admin:verify-otp", current_app=self.name))

        mark_admin_2fa_pending(
            request,
            next_url=request.session.get("admin_2fa_next_url", reverse("admin:index", current_app=self.name)),
        )
        log_admin_security_event(
            action=AuditAction.CHALLENGE,
            request=request,
            user=user,
            reason="Admin OTP challenge resent successfully.",
            resource_type="admin_otp_resend",
            resource_id=str(user.pk),
        )
        messages.success(request, "Yeni OTP kodu email ünvanınıza göndərildi.")
        return redirect(reverse("admin:verify-otp", current_app=self.name))
