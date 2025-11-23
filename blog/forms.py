# blog/forms.py
from django import forms
from django.contrib.auth.models import User


class SubscriptionForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label='',  # Etiket lazım deyil, placeholder istifadə edəcəyik
        widget=forms.EmailInput(attrs={
            'placeholder': 'Email ünvanınızı daxil edin...',
            'class': 'form-control',  # Bootstrap və ya öz CSS-imiz üçün
            'id': 'emailInput',
        })
    )
    # Əgər gələcəkdə ad/soyad da istəsəniz bura əlavə edə bilərsiniz.


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label='Şifrə',
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Şifrənizi daxil edin...',
            'class': 'form-control',
        })
    )
    password2 = forms.CharField(
        label='Şifrə təkrar',
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Şifrəni təkrar daxil edin...',
            'class': 'form-control',
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email')
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'İstifadəçi adınız...',
                'class': 'form-control',
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'Email ünvanınız...',
                'class': 'form-control',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Şifrələr uyğun gəlmir")

        return cleaned_data
