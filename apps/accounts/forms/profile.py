"""
Profile-related forms (accounts app).
"""

from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.utils.translation import gettext_lazy as _


def _password_attrs(placeholder, autocomplete):
    return {
        "class": "form-control",
        "placeholder": placeholder,
        "autocomplete": autocomplete,
        "autocapitalize": "none",
        "autocorrect": "off",
        "spellcheck": "false",
    }


class CustomPasswordChangeForm(PasswordChangeForm):
    """Styled password change form for the profile cabinet."""

    old_password = forms.CharField(
        label=_("Mövcud şifrə"),
        strip=False,
        widget=forms.PasswordInput(attrs=_password_attrs(_("Mövcud şifrə"), "current-password")),
    )
    new_password1 = forms.CharField(
        label=_("Yeni şifrə"),
        strip=False,
        widget=forms.PasswordInput(attrs=_password_attrs(_("Yeni şifrə"), "new-password")),
    )
    new_password2 = forms.CharField(
        label=_("Yeni şifrəni təkrarla"),
        strip=False,
        widget=forms.PasswordInput(attrs=_password_attrs(_("Yeni şifrəni təkrarla"), "new-password")),
    )
