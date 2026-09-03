"""
OTP (one-time-password) forms for the accounts app.

Contains forms that require an emailed OTP code as part of an authentication
or account-recovery flow.
"""

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import SetPasswordForm
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.accounts.identity import user_access_is_login_blocked
from apps.accounts.models import EmailOTP
from core.utils import get_auth_otp_max_attempts

from ..services import verify_otp_code


def _password_reset_password_attrs(placeholder):
    return {
        "class": "form-control",
        "placeholder": placeholder,
        "autocomplete": "new-password",
        "autocapitalize": "none",
        "autocorrect": "off",
        "spellcheck": "false",
    }


def mark_self_service_password_set(user):
    """İlk-giriş qapısını bağla — istifadəçi hər iki şərti ÖZÜ ödəyib (R-8).

    ``FirstLoginPasswordMiddleware`` ``password_change_required`` qalxıq
    olduqca istifadəçini ``/accounts/set-password/``-a qaytarır; o səhifənin
    tələbi isə məhz budur: e-poçtuna gələn OTP-ni təsdiqlə və ÖZ parolunu qur
    (bax ``views/auth/first_login.py``).  Parol bərpası bunların ikisini də
    edir, ona görə köçürülmüş hesab bərpadan sonra eyni qapıda İKİNCİ dəfə
    saxlanılmır.  RİM-in verdiyi müvəqqəti parol yolu TOXUNMUR: orada parolu
    operator qoyur, e-poçt sahibliyi sübut olunmur — bayraq qalxıq qalır.
    """

    profile = getattr(user, "profile", None)
    if profile is None:
        return
    changed = []
    if profile.password_change_required:
        profile.password_change_required = False
        changed.append("password_change_required")
    if not profile.email_verified:
        profile.email_verified = True
        changed.append("email_verified")
    if changed:
        profile.save(update_fields=changed + ["updated_at"])


def _password_reset_otp_attrs():
    return {
        "class": "form-control",
        "placeholder": pgettext_lazy(
            "accounts.form.password_reset_otp.placeholder",
            "otp_code",
        ),
        "inputmode": "numeric",
        "autocomplete": "one-time-code",
        "maxlength": "6",
    }


class OTPPasswordResetConfirmForm(SetPasswordForm):
    """Set-password form that requires the emailed OTP code as well."""

    otp_code = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "otp_code"),
        max_length=6,
        widget=forms.TextInput(attrs=_password_reset_otp_attrs()),
    )
    new_password1 = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "new_password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs=_password_reset_password_attrs(
                pgettext_lazy("accounts.form.password_reset_otp.placeholder", "new_password")
            )
        ),
    )
    new_password2 = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "new_password_confirm"),
        strip=False,
        widget=forms.PasswordInput(
            attrs=_password_reset_password_attrs(
                pgettext_lazy("accounts.form.password_reset_otp.placeholder", "new_password_confirm")
            )
        ),
    )

    def clean_otp_code(self):
        candidate = (self.cleaned_data.get("otp_code") or "").strip()
        success, otp = verify_otp_code(self.user, candidate, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        if not success or otp is None:
            raise forms.ValidationError(pgettext_lazy("accounts.form.password_reset_otp.error", "otp_invalid"))
        self.matched_otp = otp
        return candidate

    def save(self, commit=True):
        user = super().save(commit=commit)
        mark_self_service_password_set(user)
        matched_otp = getattr(self, "matched_otp", None)
        if matched_otp is not None and not matched_otp.is_used:
            matched_otp.is_used = True
            matched_otp.is_verified = True
            matched_otp.save(update_fields=["is_used", "is_verified"])
        EmailOTP.objects.filter(
            user=user,
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            is_used=False,
        ).exclude(
            pk=getattr(matched_otp, "pk", None)
        ).update(is_used=True)
        return user


class OTPPasswordResetCodeForm(forms.Form):
    """Password reset form completed with only the emailed OTP code."""

    email = forms.EmailField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "email"),
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": pgettext_lazy(
                    "accounts.form.password_reset_otp.placeholder",
                    "email",
                ),
                "autocomplete": "email",
            }
        ),
    )
    otp_code = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "otp_code"),
        max_length=6,
        widget=forms.TextInput(attrs=_password_reset_otp_attrs()),
    )
    new_password1 = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "new_password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs=_password_reset_password_attrs(
                pgettext_lazy("accounts.form.password_reset_otp.placeholder", "new_password")
            )
        ),
    )
    new_password2 = forms.CharField(
        label=pgettext_lazy("accounts.form.password_reset_otp.label", "new_password_confirm"),
        strip=False,
        widget=forms.PasswordInput(
            attrs=_password_reset_password_attrs(
                pgettext_lazy("accounts.form.password_reset_otp.placeholder", "new_password_confirm")
            )
        ),
    )

    error_messages = {
        "otp_invalid": pgettext_lazy("accounts.form.password_reset_otp.error", "otp_invalid"),
        "password_mismatch": pgettext_lazy("accounts.form.password_reset_otp.error", "password_mismatch"),
    }

    def __init__(self, *args, email="", **kwargs):
        self.session_email = EmailOTP.normalize_email(email)
        self.user = None
        self.matched_otp = None
        super().__init__(*args, **kwargs)
        if self.session_email:
            self.fields["email"].required = False
            self.fields["email"].initial = self.session_email
            self.fields["email"].widget = forms.HiddenInput()

    def clean_otp_code(self):
        return "".join(character for character in str(self.cleaned_data.get("otp_code") or "") if character.isdigit())

    def clean(self):
        cleaned_data = super().clean()
        email = EmailOTP.normalize_email(cleaned_data.get("email") or self.session_email)
        otp_code = cleaned_data.get("otp_code") or ""
        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")

        if not email or not otp_code:
            return cleaned_data

        if password1 and password2 and password1 != password2:
            self.add_error("new_password2", self.error_messages["password_mismatch"])
            return cleaned_data

        matched_otp = self._get_valid_otp(email=email, code=otp_code)
        if matched_otp is None:
            self.add_error("otp_code", self.error_messages["otp_invalid"])
            return cleaned_data

        # R-8: ``has_usable_password()`` QƏSDƏN yoxlanmır — köçürülmüş hesabın
        # parolu məhz «unusable»-dir və bu formanın işi ona İLK parolu qoymaqdır.
        # Girişin açıq olması (``is_active`` + ``access_state``) tək meyardır;
        # OTP-nin özü e-poçt sahibliyinin sübutudur.
        user = getattr(matched_otp, "user", None)
        if user is None or not user.is_active or user_access_is_login_blocked(user):
            self.add_error("otp_code", self.error_messages["otp_invalid"])
            return cleaned_data

        if password1:
            try:
                password_validation.validate_password(password1, user)
            except forms.ValidationError as error:
                self.add_error("new_password1", error)
                return cleaned_data

        self.user = user
        self.matched_otp = matched_otp
        return cleaned_data

    def _get_valid_otp(self, *, email, code):
        pending = list(
            EmailOTP.pending_queryset(
                email=email,
                purpose=EmailOTP.Purpose.PASSWORD_RESET,
            )
            .select_related("user")
            .order_by("-created_at")[:10]
        )
        latest = pending[0] if pending else None
        if latest is None:
            return None

        if latest.is_expired():
            latest.invalidate()
            return None

        if int(latest.attempts_count or 0) >= get_auth_otp_max_attempts():
            latest.invalidate()
            return None

        matched = next((otp for otp in pending if otp.expires_at >= timezone.now() and otp.matches_code(code)), None)
        if matched is None:
            latest.register_failed_attempt()
            return None

        return matched

    def save(self, commit=True):
        if self.user is None:
            raise ValueError("Cannot save password reset form before validation.")

        self.user.set_password(self.cleaned_data["new_password1"])
        if commit:
            self.user.save()
            mark_self_service_password_set(self.user)

        matched_otp = self.matched_otp
        if matched_otp is not None and not matched_otp.is_used:
            matched_otp.is_used = True
            matched_otp.is_verified = True
            matched_otp.save(update_fields=["is_used", "is_verified"])
        EmailOTP.objects.filter(
            email=EmailOTP.normalize_email(self.cleaned_data.get("email") or self.session_email),
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            is_used=False,
        ).exclude(pk=getattr(matched_otp, "pk", None)).update(is_used=True)
        return self.user
