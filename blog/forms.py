# blog/forms.py
from django import forms
from django.contrib.auth.models import User

from .models import Post, Comment


class SubscriptionForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label='',
        widget=forms.EmailInput(attrs={
            "placeholder": "Email ünvanınızı daxil edin...",
            "class": "form-control",
            "id": "emailInput",
        })
    )
    # Gələcəkdə ad/soyad sahələri də əlavə edə bilərsən.


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Şifrənizi daxil edin...",
            "class": "form-control",
        })
    )
    password2 = forms.CharField(
        label="Şifrə təkrar",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Şifrəni təkrar daxil edin...",
            "class": "form-control",
        })
    )

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(attrs={
                "placeholder": "İstifadəçi adınız...",
                "class": "form-control",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "Email ünvanınız...",
                "class": "form-control",
            }),
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


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["title", "category", "excerpt", "content", "image_url"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Məqalə başlığı",
            }),
            "category": forms.Select(attrs={
                "class": "form-control",
            }),
            "excerpt": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Qısa təsvir (excerpt)...",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 8,
                "placeholder": "Məqalə mətni...",
            }),
            "image_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "Şəklin URL-i (məs: https://...)",
            }),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text", "rating"]
        widgets = {
            "text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Fikrini yaz...",
            }),
            "rating": forms.Select(attrs={
                "class": "form-control",
            }),
        }
