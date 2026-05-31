"""
Profile-related forms (accounts app).
"""

from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.utils.translation import gettext_lazy as _


class CustomPasswordChangeForm(PasswordChangeForm):
    """Styled password change form for the profile cabinet."""

    old_password = forms.CharField(
        label=_("Mövcud şifrə"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": _("Mövcud şifrə"),
                "autocomplete": "current-password",
            }
        ),
    )
    new_password1 = forms.CharField(
        label=_("Yeni şifrə"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": _("Yeni şifrə"),
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label=_("Yeni şifrəni təkrarla"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": _("Yeni şifrəni təkrarla"),
                "autocomplete": "new-password",
            }
        ),
    )
