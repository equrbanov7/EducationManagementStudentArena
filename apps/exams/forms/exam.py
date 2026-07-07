"""
Exam-level forms (teacher-facing).
"""

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.exams.features import (
    PRACTICAL_EXAM_TYPE,
    exam_supervision_enabled,
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
            "exam_type_extended",
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
            "fair_question_distribution_enabled",
            "ai_difficulty_balance_enabled",
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
            "exam_type_extended": forms.Select(
                attrs={
                    "class": "form-select bootstrap-single-select__native js-bootstrap-single-select",
                    "data-bootstrap-select": "",
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
            "fair_question_distribution_enabled": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "ai_difficulty_balance_enabled": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }
        labels = {
            "title": pgettext_lazy("exams.form.exam.label", "title"),
            "description": pgettext_lazy("exams.form.exam.label", "description"),
            "exam_type": pgettext_lazy("exams.form.exam.label", "exam_type"),
            "exam_type_extended": pgettext_lazy("exams.form.exam.label", "exam_type_extended"),
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
            "fair_question_distribution_enabled": pgettext_lazy(
                "exams.form.exam.label",
                "Sual təkrarını azalt",
            ),
            "ai_difficulty_balance_enabled": pgettext_lazy(
                "exams.form.exam.label",
                "AI ağırlıq balansı",
            ),
            "max_attempts_per_user": pgettext_lazy("exams.form.exam.label", "max_attempts_per_user"),
        }
        help_texts = {
            "random_question_count": pgettext_lazy("exams.form.exam.help", "random_question_count"),
            "fair_question_distribution_enabled": pgettext_lazy(
                "exams.form.exam.help",
                "Eyni sualın çox tələbəyə düşməməsi və blokların mümkün qədər növbəli paylanması üçün.",
            ),
            "ai_difficulty_balance_enabled": pgettext_lazy(
                "exams.form.exam.help",
                "AI sual çətinliyini yoxlayır və hər tələbəyə oxşar ağırlıqda sual dəsti verməyə çalışır.",
            ),
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
        self.exam_supervision_enabled = exam_supervision_enabled()

        submitted_exam_type = (self.data.get("exam_type") or "").strip() if self.is_bound else ""
        if not self.practical_exams_enabled and submitted_exam_type != PRACTICAL_EXAM_TYPE:
            self.fields["exam_type"].choices = selectable_exam_type_choices(self.fields["exam_type"].choices)

        # İmtahan kateqoriyası (Final/Kollekvium/Sınaq) — opsionaldır. Boş seçim
        # üçün oxunaqlı etiket veririk ki, həm create, həm də edit-də düzgün
        # önseçilsin (model sahəsi blank=True/null=True olduğu üçün required deyil).
        if "exam_type_extended" in self.fields:
            self.fields["exam_type_extended"].required = False
            common_category_values = {"quiz", "midterm", "final"}

            # FINAL kateqoriyası yalnız imtahan mərkəzinə aiddir: müəllim final
            # imtahan yarada/çevirə bilməz (mövcud final instansı redaktədə
            # seçim kimi qalır ki, forma partlamasın — clean() yenə qoruyur).
            from apps.exams.services.access_policy import FINAL_EXAM_CATEGORY, can_manage_final_exam_content

            self._can_manage_final_exams = user is None or can_manage_final_exam_content(user)
            if not self._can_manage_final_exams:
                common_category_values = common_category_values - {FINAL_EXAM_CATEGORY}

            current_category_value = (
                self.initial.get("exam_type_extended")
                or getattr(getattr(self, "instance", None), "exam_type_extended", "")
                or ""
            )
            extended_choices = [
                choice
                for choice in self.fields["exam_type_extended"].choices
                if choice[0] in common_category_values
                or (current_category_value and choice[0] == current_category_value)
            ]
            self.fields["exam_type_extended"].choices = [
                ("", pgettext_lazy("exams.form.exam.placeholder", "exam_type_extended_none"))
            ] + extended_choices

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
        self.fields["random_question_count"].help_text = (
            "0 yazsan, bütün aktiv suallar düşəcək. Boş qalarsa standart 10 qəbul olunur. "
            "Test, yazılı və praktiki imtahanlara aiddir."
        )
        self.fields["fair_question_distribution_enabled"].help_text = (
            "Eyni sualın çox tələbəyə düşməməsi, mümkün olduqca hər tələbəyə fərqli sualların "
            "və kifayət qədər blok varsa fərqli blokların düşməsi üçün."
        )
        self.fields["ai_difficulty_balance_enabled"].help_text = (
            "AI sualların ağırlıq dərəcəsini yoxlayır və tələbələrə oxşar çətinlikdə sual dəsti "
            "düşməsinə çalışır. AI açarı yoxdursa mövcud difficulty dəyərləri istifadə olunur."
        )
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

        # Yeni imtahan yaradılarkən defaultlar (imtahan mərkəzi kabinetdə yaradarkən):
        #   • aktiv seçili;
        #   • sual sayı = 50;
        #   • cəhd sayı = 1;
        #   • is_public = False → imtahan HAMIYA AÇIQ deyil, BAĞLI görünür.
        if not self.instance.pk and not self.is_bound:
            self.fields["is_active"].initial = True
            self.initial.setdefault("is_active", True)
            self.fields["random_question_count"].initial = 50
            self.initial.setdefault("random_question_count", 50)
            self.fields["max_attempts_per_user"].initial = 1
            self.initial.setdefault("max_attempts_per_user", 1)
            self.fields["is_public"].initial = False
            self.initial.setdefault("is_public", False)
            self.fields["fair_question_distribution_enabled"].initial = True
            self.initial.setdefault("fair_question_distribution_enabled", True)
            self.fields["ai_difficulty_balance_enabled"].initial = False
            self.initial.setdefault("ai_difficulty_balance_enabled", False)
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

    def clean_exam_type_extended(self):
        value = self.cleaned_data.get("exam_type_extended") or None
        if value == "final" and not getattr(self, "_can_manage_final_exams", True):
            # Mövcud final imtahanın redaktəsində dəyər dəyişmirsə icazə ver;
            # müəllimin YENİ final yaratması / finala çevirməsi qadağandır.
            current_value = getattr(getattr(self, "instance", None), "exam_type_extended", None)
            if current_value != "final":
                raise forms.ValidationError(
                    pgettext_lazy("exams.form.exam.error", "final_exam_category_exam_center_only")
                )
        return value

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
                existing_value = self.instance.random_question_count
                return 10 if existing_value is None else existing_value
            return 10
        return value

    def _clean_enabled_toggle(self, field_name, *, default):
        value = bool(self.cleaned_data.get(field_name))
        if self.is_bound and field_name not in self.data:
            if self.instance.pk:
                return bool(getattr(self.instance, field_name, default))
            return default
        return value

    def clean_fair_question_distribution_enabled(self):
        return self._clean_enabled_toggle("fair_question_distribution_enabled", default=True)

    def clean_ai_difficulty_balance_enabled(self):
        return self._clean_enabled_toggle("ai_difficulty_balance_enabled", default=False)

    @staticmethod
    def _ensure_local_aware(value):
        """
        `datetime-local` input naive gəlir. İstifadəçinin seçdiyi saat onun yerli
        vaxtıdır (TIME_ZONE = Asia/Baku) — onu açıq şəkildə cari zona ilə aware
        edirik ki, DB sürücüsü naive dəyəri UTC kimi saxlayıb 4 saat sürüşmə
        yaratmasın. Aware gəlibsə, toxunmuruq.
        """
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_start_datetime(self):
        return self._ensure_local_aware(self.cleaned_data.get("start_datetime"))

    def clean_end_datetime(self):
        return self._ensure_local_aware(self.cleaned_data.get("end_datetime"))

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

        # Əgər hər ikisi doldurulubsa, bitmə başlamadan sonra olmalıdır
        if start_dt and end_dt:
            if start_dt >= end_dt:
                raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "end_after_start"))

        return cleaned_data
