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

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password1")
        # Cari parolla eyni parol «yeniləmə» deyil (QA-1 F12). Yalnız cari parol DÜZGÜN yazılıbsa deyilir
        # (``old_password`` səhvdirsə cleaned_data-da yoxdur) — əks halda səhv təxmin «bu cari paroldur» ilə təsdiqlənərdi.
        if password and cleaned.get("old_password") and not self.errors and self.user.check_password(password):
            self.add_error(
                "new_password1",
                forms.ValidationError(
                    _("Yeni şifrə cari şifrədən fərqli olmalıdır."),
                    code="password_unchanged",
                ),
            )
        return cleaned
