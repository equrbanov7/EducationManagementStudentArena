# blog/forms.py
from django import forms
from django.contrib.auth.models import User



from .models import Post, Comment, Question


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
    # Modeldə olmayan, amma yeni kateqoriya yaratmaq üçün lazım olan sahə
    new_category = forms.CharField(
        label="Yeni Kateqoriya",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Siyahıda yoxdursa, yenisini bura yazın..."
        })
    )

    class Meta:
        model = Post
        fields = ["title", "category", "excerpt", "content", "image_url","image"] # new_category bura daxil edilmir!
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
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Kateqoriya seçimini məcburi etmirik (istifadəçi yenisini yaza bilsin deyə)
        self.fields['category'].required = False
        self.fields['category'].empty_label = "--- Kateqoriya Seçin ---"
        #Image və image_url sahələrindən yalnız biri doldurulmalıdır
        self.fields['image'].required = False
        self.fields['image_url'].required = False


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

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["question_text", "answer_text", "visible_to_all", "visible_users"]
        widgets = {
            "question_text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Sual mətni...",
            }),
            "answer_text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Cavab mətni (istəyə görə)...",
            }),
            "visible_to_all": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "visible_users": forms.SelectMultiple(attrs={
                "class": "form-control",
            }),
        }
        labels = {
            "question_text": "Sual",
            "answer_text": "Cavab",
            "visible_to_all": "Hamı görə bilsin?",
            "visible_users": "Görə bilən istifadəçilər (əgər hamı deyilsə)",
        }



