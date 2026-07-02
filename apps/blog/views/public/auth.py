# blog/views/auth.py

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from apps.accounts.models import EmailOTP
from apps.accounts.public import issue_email_otp, purge_stale_pending_registration
from core.utils import get_auth_otp_expiry_seconds

from ...forms import RegisterForm
from ...utils import send_verify_email

User = get_user_model()
signer = TimestampSigner()
logger = logging.getLogger(__name__)


def register_view(request):
    if request.method == "POST":
        # Remove any prior unverified registration so the form's unique-constraint
        # check does not block a legitimate retry after a failed OTP delivery.
        purge_stale_pending_registration(
            username=request.POST.get("username", "").strip(),
            email=request.POST.get("email", "").strip(),
        )

        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # password set
            password = form.cleaned_data["password"]
            user.set_password(password)

            # email təsdiqlənənə qədər giriş qadağan
            user.is_active = False
            user.save()

            code, expires_at, _otp = issue_email_otp(user, purpose=EmailOTP.Purpose.SIGNUP)
            try:
                send_verify_email(user, code, request=request, expires_at=expires_at)
            except Exception:
                logger.exception("Failed to send OTP email during blog registration for user pk=%s", user.pk)
                # Roll back: delete the user so the credentials are free to retry.
                user.delete()
                messages.error(request, pgettext("blog.verify.message", "otp_email_send_failed"))
                return render(request, "blog/register.html", {"form": form})

            request.session["pending_verify_email"] = user.email
            messages.success(request, pgettext("blog.verify.message", "code_sent"))
            return redirect("verify_code")
    else:
        form = RegisterForm()

    return render(request, "blog/register.html", {"form": form})


def verify_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext("blog.verify.message", "pending_email_missing"))
        return redirect("register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, pgettext("blog.verify.message", "user_not_found"))
            return redirect("register")

        otp = EmailOTP.get_matching_otp(user=user, code=code, purpose=EmailOTP.Purpose.SIGNUP)
        if not otp or otp.is_expired():
            messages.error(request, pgettext("blog.verify.message", "invalid_or_expired_code"))
            return render(request, "blog/verify_code.html", {"email": email})

        otp.is_used = True
        otp.is_verified = True
        otp.save(update_fields=["is_used", "is_verified"])

        user.is_active = True
        user.save()

        messages.success(request, pgettext("blog.verify.message", "email_verified"))
        return redirect("login")

    return render(request, "blog/verify_code.html", {"email": email})


def verify_email_link_view(request):
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=get_auth_otp_expiry_seconds())
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        messages.success(request, pgettext("blog.verify.message", "email_verified"))
        return redirect("login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, pgettext("blog.verify.message", "invalid_or_expired_link"))
        return redirect("register")


def resend_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext("blog.verify.message", "email_missing"))
        return redirect("register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, pgettext("blog.verify.message", "user_not_found"))
        return redirect("register")

    code, expires_at, _otp = issue_email_otp(user, purpose=EmailOTP.Purpose.SIGNUP)
    send_verify_email(user, code, request=request, expires_at=expires_at)

    messages.success(request, pgettext("blog.verify.message", "new_code_sent"))
    return redirect("verify_code")


def logout_view(request):
    """
    İstifadəçini çıxış etdirib ana səhifəyə yönləndirir.
    """
    logout(request)
    return redirect("home")
