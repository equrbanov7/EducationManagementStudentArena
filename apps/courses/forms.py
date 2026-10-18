"""
courses/forms.py
────────────────
Kurs yaratma, redaksiya, mövzu əlavə etmə üçün formalar.

Nə üçün:
- HTML forma yaratmaq (Bootstrap stilləmə ilə)
- Validasiya (cleaners)
- CSRF protection (otomatik)
"""

from urllib.parse import urlsplit

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import pgettext, pgettext_lazy

from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

from .models import Course, CourseResource, CourseTopic
from .resource_upload import LINK_KIND, kind_label, prepare_resource_file

# Kurs statusunun TƏRCÜMƏ olunan etiketləri (2026-09-28). Modeldəki
# `Course.STATUS_CHOICES` etiketləri sərt kodlanmış AZ-dır («Draft (yayımlanmayıb)»)
# və dil dəyişəndə qalırdı; modeli dəyişmək miqrasiya tələb edir, ona görə forma
# və şablonlar bu siyahını işlədir.
COURSE_STATUS_CHOICES = (
    ("draft", pgettext_lazy("courses.course_status", "draft")),
    ("published", pgettext_lazy("courses.course_status", "published")),
    ("archived", pgettext_lazy("courses.course_status", "archived")),
)


# ════════════════════════════════════════════════════════════════════════════
# COURSE FORM (Kurs Yaratma/Redaksiya)
# ════════════════════════════════════════════════════════════════════════════


class CourseForm(forms.ModelForm):
    """
    Kurs yaratma/redaksiya forması.

    Nə edər:
    1. Müəllim kurs adı, təsviri, şəkli daxil edir
    2. Form validasiya edir (boşluqları yoxlayır)
    3. Kurs yaradılır/redaktə olunur

    Misal (Template):
    <form method="post">
        {{ form.title }}
        {{ form.description }}
        {{ form.cover_image }}
        <button>Kurs Yarat</button>
    </form>
    """

    organization = forms.ModelChoiceField(
        queryset=apps.get_model("organizations", "Organization").objects.none(),
        required=False,
        label=pgettext_lazy("courses.form.course.label", "organization"),
        empty_label=pgettext_lazy("courses.form.course.placeholder", "select_organization"),
    )

    def __init__(self, *args, **kwargs):
        allow_organization_selection = kwargs.pop("allow_organization_selection", False)
        organization_queryset = kwargs.pop("organization_queryset", None)
        initial_organization = kwargs.pop("initial_organization", None)
        super().__init__(*args, **kwargs)
        self._clear_missing_cover_image = False
        if "status" in self.fields:
            self.fields["status"].choices = COURSE_STATUS_CHOICES

        if allow_organization_selection:
            from apps.organizations.models import Organization

            self.fields["organization"].queryset = (
                organization_queryset
                if organization_queryset is not None
                else Organization.objects.filter(is_active=True, status="active").order_by("name")
            )
            self.fields["organization"].required = True
            self.fields["organization"].widget.attrs.update(
                {
                    "class": "form-control",
                }
            )
            if initial_organization is not None:
                self.fields["organization"].initial = initial_organization
        else:
            self.fields.pop("organization", None)

    class Meta:
        model = Course
        fields = ["title", "description", "cover_image", "status"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("courses.form.course.placeholder", "title"),
                    "required": True,
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("courses.form.course.placeholder", "description"),
                    "rows": 4,
                }
            ),
            "cover_image": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def clean_title(self):
        """Title validasiyası."""
        title = self.cleaned_data.get("title", "").strip()

        if len(title) < 3:
            raise forms.ValidationError(pgettext_lazy("courses.form.course.error", "title_min_length"))

        if len(title) > 255:
            raise forms.ValidationError(pgettext_lazy("courses.form.course.error", "title_max_length"))

        return title

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get("cover_image")
        if not cover_image:
            return cover_image

        if not isinstance(cover_image, UploadedFile):
            name = getattr(cover_image, "name", "")
            if not name:
                return None
            try:
                if cover_image.storage.exists(name):
                    return cover_image
            except Exception:
                pass
            self._clear_missing_cover_image = True
            return None

        validate_uploaded_file(
            cover_image,
            allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
            max_size_mb=10,
            allowed_mime_types=set(),
            allowed_mime_prefixes=("image/",),
        )
        randomize_uploaded_filename(cover_image)
        return cover_image

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._clear_missing_cover_image:
            instance.cover_image = None

        if commit:
            instance.save()
            self.save_m2m()

        return instance


# ════════════════════════════════════════════════════════════════════════════
# COURSE TOPIC FORM (Mövzu Əlavə Etmə)
# ════════════════════════════════════════════════════════════════════════════


class CourseTopicForm(forms.ModelForm):
    """
    Mövzu əlavə etmə forması.

    Nə edər:
    - Müəllim mövzu adı, sıra, açıqlaması daxil edir
    - Order otomatik hesablanır (sonuncu mövzu + 1)

    Misal:
    - Course: Python 101
    - Topic 1: Həftə 1: Giriş (order=1)
    - Topic 2: Həftə 2: Dəyişkənlər (order=2)
    """

    class Meta:
        model = CourseTopic
        fields = ["title", "description"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("courses.form.topic.placeholder", "title"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("courses.form.topic.placeholder", "description"),
                }
            ),
        }

    def clean_title(self):
        """Title validasiyası."""
        title = self.cleaned_data.get("title", "").strip()

        if not title:
            raise forms.ValidationError(pgettext_lazy("courses.form.topic.error", "title_required"))

        return title


# ════════════════════════════════════════════════════════════════════════════
# COURSE RESOURCE FORM (Resurs Əlavə Etmə)
# ════════════════════════════════════════════════════════════════════════════


class CourseResourceForm(forms.ModelForm):
    """
    Resurs əlavə etmə forması (Fayl / Link / Video / Sənəd).

    2026-10-19: format və ölçü SEÇİLƏN TİPƏ görədir (``apps/courses/resource_upload.py``) —
    Video: MP4/MOV/WEBM/M4V ≤ 200 MB, Sənəd: ofis/PDF/ODT/TXT ≤ 50 MB, Fayl: sənəd + arxiv +
    şəkil ≤ 100 MB; Link: yalnız http/https URL. Xətalar sahəyə bağlıdır (``file`` / ``url``)
    və modalda göstərilir.
    """

    class Meta:
        model = CourseResource
        fields = ["title", "description", "resource_type", "file", "url", "topic"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("courses.form.resource.placeholder", "title"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": pgettext_lazy("courses.form.resource.placeholder", "description"),
                }
            ),
            "resource_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "file": forms.FileInput(attrs={"class": "form-control"}),
            "url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("courses.form.resource.placeholder", "url"),
                }
            ),
            "topic": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def clean_url(self):
        url = (self.cleaned_data.get("url") or "").strip()
        if url and urlsplit(url).scheme.lower() not in ("http", "https"):
            raise forms.ValidationError(
                pgettext("courses.resource_upload", "Link http:// və ya https:// ilə başlamalıdır.")
            )
        return url

    def clean(self):
        cleaned_data = super().clean()
        kind = cleaned_data.get("resource_type")
        if not kind:
            return cleaned_data  # tip xətası artıq sahəyə yazılıb
        file = cleaned_data.get("file")
        url = cleaned_data.get("url")

        if kind == LINK_KIND:
            if file:
                self.add_error(
                    "file",
                    pgettext(
                        "courses.resource_upload",
                        "«Link» tipində fayl yüklənmir — fayl üçün «Fayl», «Video» və ya «Sənəd» seçin.",
                    ),
                )
            if not url and "url" not in self.errors:
                self.add_error(
                    "url", pgettext("courses.resource_upload", "Link üçün URL daxil edin (http:// və ya https://).")
                )
            return cleaned_data

        if url:
            self.add_error(
                "url",
                pgettext("courses.resource_upload", "Bu tipdə fayl yüklənir — xarici link üçün «Link» tipini seçin."),
            )
        if not file:
            if "file" not in self.errors:
                self.add_error(
                    "file",
                    pgettext("courses.resource_upload", "«{kind}» üçün fayl seçin.").format(kind=kind_label(kind)),
                )
            return cleaned_data
        try:
            prepare_resource_file(file, kind)
        except ValidationError as error:
            self.add_error("file", error)
        return cleaned_data
