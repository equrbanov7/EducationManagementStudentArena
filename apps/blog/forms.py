# blog/forms.py
from django import forms
from django.contrib.auth.models import User
from django.utils.translation import pgettext_lazy

from .models import Comment, Post, Question


class SubscriptionForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label="",
        widget=forms.EmailInput(
            attrs={
                "placeholder": pgettext_lazy("blog.form.subscription", "email_placeholder"),
                "class": "form-control",
                "id": "emailInput",
            }
        ),
    )


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label=pgettext_lazy("blog.form.register", "password_label"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": pgettext_lazy("blog.form.register", "password_placeholder"),
                "class": "form-control",
            }
        ),
    )
    password2 = forms.CharField(
        label=pgettext_lazy("blog.form.register", "password_confirm_label"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": pgettext_lazy("blog.form.register", "password_confirm_placeholder"),
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "placeholder": pgettext_lazy("blog.form.register", "username_placeholder"),
                    "class": "form-control",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": pgettext_lazy("blog.form.register", "email_placeholder"),
                    "class": "form-control",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError(pgettext_lazy("blog.form.register", "password_mismatch"))

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError(pgettext_lazy("blog.form.register", "email_exists"))
        return email


class PostForm(forms.ModelForm):
    new_category = forms.CharField(
        label=pgettext_lazy("blog.form.post", "new_category_label"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": pgettext_lazy("blog.form.post", "new_category_placeholder"),
            }
        ),
    )

    class Meta:
        model = Post
        fields = [
            "title",
            "category",
            "excerpt",
            "content",
            "image_url",
            "image",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("blog.form.post", "title_placeholder"),
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "excerpt": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("blog.form.post", "excerpt_placeholder"),
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 8,
                    "placeholder": pgettext_lazy("blog.form.post", "content_placeholder"),
                }
            ),
            "image_url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("blog.form.post", "image_url_placeholder"),
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = False
        self.fields["category"].empty_label = pgettext_lazy("blog.form.post", "category_empty_label")
        self.fields["image"].required = False
        self.fields["image_url"].required = False


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text", "rating"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("blog.form.comment", "text_placeholder"),
                }
            ),
            "rating": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["question_text", "answer_text", "visible_to_all", "visible_users"]
        widgets = {
            "question_text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("blog.form.question", "question_placeholder"),
                }
            ),
            "answer_text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("blog.form.question", "answer_placeholder"),
                }
            ),
            "visible_to_all": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "visible_users": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),
        }
        labels = {
            "question_text": pgettext_lazy("blog.form.question", "label_question"),
            "answer_text": pgettext_lazy("blog.form.question", "label_answer"),
            "visible_to_all": pgettext_lazy("blog.form.question", "label_visible_to_all"),
            "visible_users": pgettext_lazy("blog.form.question", "label_visible_users"),
        }
