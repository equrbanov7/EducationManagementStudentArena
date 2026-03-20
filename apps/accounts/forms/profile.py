"""
Profile-related forms (accounts app).
"""

from django import forms
from django.contrib.auth.forms import PasswordChangeForm


class CustomPasswordChangeForm(PasswordChangeForm):
    """Styled password change form for the profile cabinet."""

    old_password = forms.CharField(
        label="Mövcud şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Mövcud şifrə",
                "autocomplete": "current-password",
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
