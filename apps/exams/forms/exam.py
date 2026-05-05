"""
Exam-level forms (teacher-facing).
"""

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext_lazy

from apps.exams.features import (
    PRACTICAL_EXAM_TYPE,
    practical_exam_disabled_message,
    practical_exams_enabled,
    selectable_exam_type_choices,
)
from apps.exams.models import CodingExamQuestion, CodingTestCase, Exam, StudentGroup

from .coding import TEST_CASE_PLACEHOLDER, dump_test_cases, parse_test_cases

User = get_user_model()


class ExamForm(forms.ModelForm):
    coding_language = forms.ChoiceField(
        choices=CodingExamQuestion.LANGUAGE_CHOICES,
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "language"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    coding_question_title = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "title"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    coding_problem_statement = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "problem_statement"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
    )
    coding_input_description = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "input_description"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    coding_output_description = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "output_description"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    coding_example_input = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "example_input"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    coding_example_output = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "example_output"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    coding_time_limit_seconds = forms.IntegerField(
        required=False,
        min_value=1,
        initial=2,
        label=pgettext_lazy("exams.form.coding.label", "time_limit"),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    )
    coding_memory_limit_mb = forms.IntegerField(
        required=False,
        min_value=16,
        initial=128,
        label=pgettext_lazy("exams.form.coding.label", "memory_limit"),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "16"}),
    )
    coding_max_score = forms.IntegerField(
        required=False,
        min_value=1,
        initial=100,
        label=pgettext_lazy("exams.form.coding.label", "maximum_score"),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
    )
    coding_starter_code = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "starter_code"),
        widget=forms.Textarea(attrs={"class": "form-control code-textarea", "rows": 8}),
    )
    coding_visible_test_cases = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "visible_test_cases"),
        help_text=pgettext_lazy("exams.form.coding.help", "visible_test_cases"),
        widget=forms.Textarea(
            attrs={
                "class": "form-control coding-testcase-json",
                "rows": 5,
                "placeholder": TEST_CASE_PLACEHOLDER,
            }
        ),
    )
    coding_hidden_test_cases = forms.CharField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "hidden_test_cases"),
        help_text=pgettext_lazy("exams.form.coding.help", "hidden_test_cases"),
        widget=forms.Textarea(
            attrs={
                "class": "form-control coding-testcase-json",
                "rows": 5,
                "placeholder": TEST_CASE_PLACEHOLDER,
            }
        ),
    )
    coding_allow_file_creation = forms.BooleanField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "allow_file_creation"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    coding_allow_multiple_files = forms.BooleanField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "allow_multiple_files"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    coding_enable_code_execution = forms.BooleanField(
        required=False,
        label=pgettext_lazy("exams.form.coding.label", "enable_code_execution"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

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
            "random_question_count",
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
                    "class": "form-select",
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
                    "lang": "en-GB",
                    "step": "60",
                    "data-hour-format": "24",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "start_datetime"),
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "lang": "en-GB",
                    "step": "60",
                    "data-hour-format": "24",
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
                    "class": "form-select",
                }
            ),
            "allowed_groups": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
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
            "random_question_count": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "random_question_count"),
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
            "random_question_count": pgettext_lazy("exams.form.exam.label", "random_question_count"),
            "max_attempts_per_user": pgettext_lazy("exams.form.exam.label", "max_attempts_per_user"),
        }
        help_texts = {
            "random_question_count": pgettext_lazy("exams.form.exam.help", "random_question_count"),
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
        self.practical_exams_enabled = practical_exams_enabled()

        submitted_exam_type = (self.data.get("exam_type") or "").strip() if self.is_bound else ""
        if not self.practical_exams_enabled and submitted_exam_type != PRACTICAL_EXAM_TYPE:
            self.fields["exam_type"].choices = selectable_exam_type_choices(self.fields["exam_type"].choices)

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
                    "class": "form-select",
                }
            )
            if initial_organization is not None:
                self.fields["organization"].initial = initial_organization
        else:
            self.fields.pop("organization", None)

        self.fields["start_datetime"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["end_datetime"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["random_question_count"].required = False
        self._coding_field_names = [
            "coding_language",
            "coding_question_title",
            "coding_problem_statement",
            "coding_input_description",
            "coding_output_description",
            "coding_example_input",
            "coding_example_output",
            "coding_time_limit_seconds",
            "coding_memory_limit_mb",
            "coding_max_score",
            "coding_starter_code",
            "coding_visible_test_cases",
            "coding_hidden_test_cases",
            "coding_allow_file_creation",
            "coding_allow_multiple_files",
            "coding_enable_code_execution",
        ]

        # Yeni imtahan yaradılarkən "aktiv" default seçili gəlsin.
        if not self.instance.pk and not self.is_bound:
            self.fields["is_active"].initial = True
            self.initial.setdefault("is_active", True)
            self.fields["random_question_count"].initial = 10
            self.initial.setdefault("random_question_count", 10)
            self.initial.setdefault("coding_language", CodingExamQuestion.LANGUAGE_PYTHON)
            self.initial.setdefault("coding_time_limit_seconds", 2)
            self.initial.setdefault("coding_memory_limit_mb", 128)
            self.initial.setdefault("coding_max_score", 100)

        if self.instance.pk and not self.is_bound and self.instance.exam_type == "coding":
            self._load_coding_question_initial()

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

    def _load_coding_question_initial(self):
        base_question = (
            self.instance.questions.filter(coding_details__isnull=False)
            .select_related("coding_details")
            .order_by("order", "id")
            .first()
        )
        if not base_question:
            return

        coding_question = base_question.coding_details
        self.initial.update(
            {
                "coding_language": coding_question.language,
                "coding_question_title": coding_question.title,
                "coding_problem_statement": coding_question.problem_statement,
                "coding_input_description": coding_question.input_description,
                "coding_output_description": coding_question.output_description,
                "coding_example_input": coding_question.example_input,
                "coding_example_output": coding_question.example_output,
                "coding_time_limit_seconds": coding_question.time_limit_seconds,
                "coding_memory_limit_mb": coding_question.memory_limit_mb,
                "coding_max_score": coding_question.max_score,
                "coding_starter_code": coding_question.starter_code,
                "coding_allow_file_creation": coding_question.allow_file_creation,
                "coding_allow_multiple_files": coding_question.allow_multiple_files,
                "coding_enable_code_execution": coding_question.enable_code_execution,
                "coding_visible_test_cases": dump_test_cases(
                    coding_question.test_cases.filter(visibility=CodingTestCase.VISIBILITY_VISIBLE)
                ),
                "coding_hidden_test_cases": dump_test_cases(
                    coding_question.test_cases.filter(visibility=CodingTestCase.VISIBILITY_HIDDEN)
                ),
            }
        )

    def _submitted_exam_type(self):
        if self.is_bound:
            return (self.data.get("exam_type") or "").strip()
        return self.initial.get("exam_type") or getattr(self.instance, "exam_type", "test")

    def clean_coding_visible_test_cases(self):
        if self._submitted_exam_type() != "coding":
            return []
        return parse_test_cases(
            self.cleaned_data.get("coding_visible_test_cases"),
            visibility=CodingTestCase.VISIBILITY_VISIBLE,
        )

    def clean_coding_hidden_test_cases(self):
        if self._submitted_exam_type() != "coding":
            return []
        return parse_test_cases(
            self.cleaned_data.get("coding_hidden_test_cases"),
            visibility=CodingTestCase.VISIBILITY_HIDDEN,
        )

    def clean_access_code(self):
        code = (self.cleaned_data.get("access_code") or "").strip()
        if not code:
            return ""  # boş buraxmaq olar

        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "access_code_invalid"))

        return code

    def clean_random_question_count(self):
        value = self.cleaned_data.get("random_question_count")
        if value in (None, ""):
            if self.instance.pk:
                return self.instance.random_question_count or 10
            return 10
        return value

    def clean(self):
        cleaned_data = super().clean()
        start_dt = cleaned_data.get("start_datetime")
        end_dt = cleaned_data.get("end_datetime")
        enable_paint = cleaned_data.get("enable_paint")
        exam_type = cleaned_data.get("exam_type")

        if exam_type != "written" and enable_paint:
            raise ValidationError(pgettext_lazy("exams.form.exam.error", "enable_paint_written_only"))

        if exam_type == PRACTICAL_EXAM_TYPE and not self.practical_exams_enabled:
            self.add_error("exam_type", practical_exam_disabled_message())

        if exam_type == "coding":
            required_coding_fields = {
                "coding_question_title": pgettext_lazy("exams.form.coding.error", "title_required"),
                "coding_problem_statement": pgettext_lazy("exams.form.coding.error", "problem_statement_required"),
            }
            for field_name, error_message in required_coding_fields.items():
                if not (cleaned_data.get(field_name) or "").strip():
                    self.add_error(field_name, error_message)

            cleaned_data["random_question_count"] = 0

        # Əgər hər ikisi doldurulubsa, bitmə başlamadan sonra olmalıdır
        if start_dt and end_dt:
            if start_dt >= end_dt:
                raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "end_after_start"))

        return cleaned_data
