"""
OTP (one-time-password) forms for the accounts app.

Contains forms that require an emailed OTP code as part of an authentication
or account-recovery flow.
"""

from django import forms
from django.contrib.auth.forms import SetPasswordForm

from apps.accounts.models import EmailOTP

from ..services import verify_otp_code


class OTPPasswordResetConfirmForm(SetPasswordForm):
    """Set-password form that requires the emailed OTP code as well."""

    otp_code = forms.CharField(
        label="OTP kodu",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Emailə gələn 6 rəqəmli kod",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="Yeni şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrə",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Yeni şifrəni təkrarla",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrəni təkrarla",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_otp_code(self):
        candidate = (self.cleaned_data.get("otp_code") or "").strip()
        success, otp = verify_otp_code(self.user, candidate, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        if not success or otp is None:
            raise forms.ValidationError("OTP kodu yanlışdır və ya vaxtı bitib.")
        self.matched_otp = otp
        return candidate

    def save(self, commit=True):
        user = super().save(commit=commit)
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
