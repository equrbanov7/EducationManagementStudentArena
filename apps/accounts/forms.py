"""
Forms for accounts app (authentication and user management).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


class RegisterForm(forms.ModelForm):
    """User registration form with email verification."""

    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Şifrənizi daxil edin...",
                "class": "form-control",
            }
        ),
    )
    password2 = forms.CharField(
        label="Şifrə təkrar",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Şifrəni təkrar daxil edin...",
                "class": "form-control",
            }
        ),
    )

    organization_type = forms.ChoiceField(
        label="Təşkilat Tipi",
        choices=[
            ("university", "Universitet"),
            ("school", "Məktəb"),
            ("course_center", "Kurs Mərkəzi"),
            ("individual", "Fərdi"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        initial="individual",
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "placeholder": "İstifadəçi adınız...",
                    "class": "form-control",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "Email ünvanınız...",
                    "class": "form-control",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "placeholder": "Adınız...",
                    "class": "form-control",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": "Soyadınız...",
                    "class": "form-control",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Şifrələr uyğun gəlmir")

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu email artıq istifadə olunur.")
        return email


class CustomLoginForm(AuthenticationForm):
    """Custom login form with styled fields."""

    username = forms.CharField(
        label="İstifadəçi adı",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "İstifadəçi adınız",
            }
        ),
    )
    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Şifrəniz",
            }
        ),
    )
