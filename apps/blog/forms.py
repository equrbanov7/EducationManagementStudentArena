# blog/forms.py
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import pgettext_lazy

from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

from .models import Category, Comment, Post, Question
from .taxonomy import SUPPORTED_CATEGORY_LANGUAGES
from .selectors import build_post_category_picker_options, get_post_category_tree
from .services import resolve_post_category_selection


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
    class LocalizedCategoryChoiceField(forms.ModelChoiceField):
        def label_from_instance(self, obj):
            return obj.localized_name

    subcategory = LocalizedCategoryChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select form-select-lg post-category-select",
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
                    "class": "form-select form-select-lg post-category-select",
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
                    "accept": ".jpg,.jpeg,.jfif,.png,.gif,.webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop("author", None)
        super().__init__(*args, **kwargs)
        category_tree = get_post_category_tree()
        root_categories = list(category_tree)
        subcategories = [child for root_category in root_categories for child in getattr(root_category, "child_categories", [])]

        self.category_tree = category_tree
        self.root_category_picker_options, self.subcategory_picker_options = build_post_category_picker_options(category_tree)
        self.fields["category"] = self.LocalizedCategoryChoiceField(
            queryset=self._queryset_from_categories(root_categories),
            label=self.fields["category"].label,
            required=True,
            widget=self.fields["category"].widget,
        )
        self.fields["subcategory"] = self.LocalizedCategoryChoiceField(
            queryset=self._queryset_from_categories(subcategories),
            label="Subcategory",
            required=False,
            widget=self.fields["subcategory"].widget,
        )
        self.fields["category"].empty_label = "Select a category"
        self.fields["subcategory"].empty_label = "Select a subcategory"
        self.fields["image"].required = False
        self.fields["image_url"].required = False
        self.selected_root_category_id, self.selected_subcategory_id = self._resolve_selected_category_ids()

    @staticmethod
    def _queryset_from_categories(categories):
        category_ids = [category.id for category in categories]
        if not category_ids:
            return Category.objects.none()
        return Category.objects.filter(id__in=category_ids).select_related("parent").order_by("sort_order", "name_en", "name_az", "id")

    def _resolve_selected_category_ids(self):
        selected_category_id = self.data.get("category") if self.is_bound else None
        selected_subcategory_id = self.data.get("subcategory") if self.is_bound else None

        if not self.is_bound and getattr(self.instance, "category_id", None):
            if self.instance.category.parent_id:
                selected_category_id = self.instance.category.parent_id
                selected_subcategory_id = self.instance.category_id
            else:
                selected_category_id = self.instance.category_id

        return self._normalize_optional_int(selected_category_id), self._normalize_optional_int(selected_subcategory_id)

    @staticmethod
    def _normalize_optional_int(raw_value):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def clean(self):
        cleaned_data = super().clean()

        if (self.data.get("new_category") or "").strip():
            raise forms.ValidationError({"category": "Categories are managed by SuperAdmin only."})

        selected_category = cleaned_data.get("category")
        selected_subcategory = cleaned_data.get("subcategory")
        cleaned_data["resolved_category"] = resolve_post_category_selection(
            category=selected_category,
            subcategory=selected_subcategory,
        )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.category = self.cleaned_data.get("resolved_category")
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        validate_uploaded_file(
            image,
            allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
            max_size_mb=int(getattr(settings, "FILE_UPLOAD_SECURITY_MAX_SIZE_MB", 25)),
            allowed_mime_types=set(),
            allowed_mime_prefixes=("image/",),
        )
        randomize_uploaded_filename(image)
        return image


class CategoryManagementForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "parent",
            "name_az",
            "name_en",
            "name_ru",
            "name_tr",
            "sort_order",
        ]
        widgets = {
            "sort_order": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "step": 1,
                }
            ),
        }

    duplicate_messages = {
        "az": "Bu Azərbaycan adı ilə eyni səviyyədə başqa kateqoriya artıq mövcuddur.",
        "en": "Bu ingilis adı ilə eyni səviyyədə başqa kateqoriya artıq mövcuddur.",
        "ru": "Bu rus adı ilə eyni səviyyədə başqa kateqoriya artıq mövcuddur.",
        "tr": "Bu türk adı ilə eyni səviyyədə başqa kateqoriya artıq mövcuddur.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(parent__isnull=True).order_by(
            "sort_order",
            "name_en",
            "name_az",
            "id",
        )
        self.fields["parent"].required = False
        self.fields["parent"].label = "Ana kateqoriya"
        self.fields["parent"].empty_label = "Ana kateqoriya seçin (boş saxlasanız əsas kateqoriya olacaq)"
        self.fields["sort_order"].required = False
        self.fields["sort_order"].label = "Sıralama"
        self.fields["sort_order"].help_text = "Kiçik rəqəm yuxarıda görünür."

        if self.instance.pk:
            invalid_parent_ids = {self.instance.pk, *self.instance.get_descendant_ids(include_self=False)}
            self.fields["parent"].queryset = self.fields["parent"].queryset.exclude(pk__in=invalid_parent_ids)

        for field_name, label in (
            ("name_az", "Ad (AZ)"),
            ("name_en", "Name (EN)"),
            ("name_ru", "Название (RU)"),
            ("name_tr", "Ad (TR)"),
        ):
            self.fields[field_name].required = True
            self.fields[field_name].label = label
            self.fields[field_name].widget.attrs.update(
                {
                    "class": "form-control",
                    "maxlength": 100,
                }
            )

        if self.instance.pk and self.instance.children.exists():
            self.fields["parent"].help_text = (
                "Bu kateqoriyanın alt kateqoriyaları var. Ona görə başqa kateqoriyanın altına keçirilə bilməz."
            )

    def clean_sort_order(self):
        return self.cleaned_data.get("sort_order") or 0

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get("parent")
        scope_filters = {"parent__isnull": True} if parent is None else {"parent": parent}
        duplicate_scope = Category.objects.filter(**scope_filters)

        if self.instance.pk:
            duplicate_scope = duplicate_scope.exclude(pk=self.instance.pk)

        for language_code in SUPPORTED_CATEGORY_LANGUAGES:
            field_name = f"name_{language_code}"
            field_value = (cleaned_data.get(field_name) or "").strip()
            if not field_value:
                continue

            if duplicate_scope.filter(**{f"{field_name}__iexact": field_value}).exists():
                self.add_error(field_name, self.duplicate_messages[language_code])

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.show_in_navbar = bool(instance.show_in_navbar and not instance.parent_id)
        if commit:
            instance.save()
        return instance


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
