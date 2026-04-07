"""
Exam-level forms (teacher-facing).
"""

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext_lazy

from apps.exams.models import Exam, StudentGroup

User = get_user_model()


class ExamForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=apps.get_model("organizations", "Organization").objects.none(),
        required=False,
        label=pgettext_lazy("exams.form.exam.label", "organization"),
        empty_label=pgettext_lazy("exams.form.exam.placeholder", "select_organization"),
    )

    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "exam_type",
            "is_active",
            "start_datetime",
            "end_datetime",
            "is_public",
            "allowed_users",
            "allowed_groups",
            "access_code",
            "total_duration_minutes",
            "default_question_time_seconds",
            "max_attempts_per_user",
            "enable_paint",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "title_example"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "description_short"),
                }
            ),
            "exam_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "start_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "start_datetime"),
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "end_datetime"),
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "is_public": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "allowed_users": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),
            "allowed_groups": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),
            "access_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "access_code"),
                    "maxlength": "6",
                }
            ),
            "total_duration_minutes": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "total_duration_minutes"),
                }
            ),
            "default_question_time_seconds": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "default_question_time_seconds"),
                }
            ),
            "max_attempts_per_user": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "max_attempts_per_user"),
                }
            ),
        }
        labels = {
            "title": pgettext_lazy("exams.form.exam.label", "title"),
            "description": pgettext_lazy("exams.form.exam.label", "description"),
            "exam_type": pgettext_lazy("exams.form.exam.label", "exam_type"),
            "is_active": pgettext_lazy("exams.form.exam.label", "is_active"),
            "start_datetime": pgettext_lazy("exams.form.exam.label", "start_datetime"),
            "end_datetime": pgettext_lazy("exams.form.exam.label", "end_datetime"),
            "is_public": pgettext_lazy("exams.form.exam.label", "is_public"),
            "allowed_users": pgettext_lazy("exams.form.exam.label", "allowed_users"),
            "allowed_groups": pgettext_lazy("exams.form.exam.label", "allowed_groups"),
            "access_code": pgettext_lazy("exams.form.exam.label", "access_code"),
            "total_duration_minutes": pgettext_lazy("exams.form.exam.label", "total_duration_minutes"),
            "default_question_time_seconds": pgettext_lazy("exams.form.exam.label", "default_question_time_seconds"),
            "max_attempts_per_user": pgettext_lazy("exams.form.exam.label", "max_attempts_per_user"),
        }

    def __init__(self, *args, **kwargs):
        """
        Teacher-ə uyğun olaraq seçimləri filtr eləmək üçün
        view-dən ExamForm(user=request.user, ...) şəklində çağırmaq məqsədi ilə.
        """
        allow_organization_selection = kwargs.pop("allow_organization_selection", False)
        organization_queryset = kwargs.pop("organization_queryset", None)
        initial_organization = kwargs.pop("initial_organization", None)
        user = kwargs.pop("user", None)
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)

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

        self.fields["start_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]

        # Yeni imtahan yaradılarkən "aktiv" default seçili gəlsin.
        if not self.instance.pk and not self.is_bound:
            self.fields["is_active"].initial = True
            self.initial.setdefault("is_active", True)

        # Default querysets
        self.fields["allowed_users"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["allowed_groups"].queryset = StudentGroup.objects.none()

        # Əgər teacher məlumatı gəlirsə, onu nəzərə alaq
        if user is not None:
            user_qs = User.objects.filter(is_active=True).exclude(id=user.id)
            if organization is not None:
                user_qs = user_qs.filter(profile__organization=organization)
                group_qs = StudentGroup.objects.filter(organization=organization)
            else:
                group_qs = StudentGroup.objects.filter(teacher=user)

            self.fields["allowed_users"].queryset = user_qs.distinct().order_by("username")
            self.fields["allowed_groups"].queryset = group_qs.order_by("name")

    def clean_access_code(self):
        code = (self.cleaned_data.get("access_code") or "").strip()
        if not code:
            return ""  # boş buraxmaq olar

        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "access_code_invalid"))

        return code

    def clean(self):
        cleaned_data = super().clean()
        start_dt = cleaned_data.get("start_datetime")
        end_dt = cleaned_data.get("end_datetime")
        enable_paint = cleaned_data.get("enable_paint")
        exam_type = cleaned_data.get("exam_type")

        if exam_type == "test" and enable_paint:
            raise ValidationError(pgettext_lazy("exams.form.exam.error", "enable_paint_written_only"))

        # Əgər hər ikisi doldurulubsa, bitmə başlamadan sonra olmalıdır
        if start_dt and end_dt:
            if start_dt >= end_dt:
                raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "end_after_start"))

        return cleaned_data
