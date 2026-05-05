"""
Question-level forms (teacher-facing).
"""

import re

from django import forms
from django.utils.translation import pgettext_lazy

from apps.exams.models import ExamQuestion, ExamQuestionOption, QuestionBlock
from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file


class ExamQuestionCreateForm(forms.ModelForm):
    """
    Bu forma test sualları üçün dinamik sayda variant yaratmaq/edit etmək üçündür.
    """

    MIN_TEST_OPTIONS = 2

    # ---- Variant field-ləri ----
    option1_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_1"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option1_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option2_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_2"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option2_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option3_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_3"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option3_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option4_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_4"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option4_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = ExamQuestion
        fields = [
            "text",
            "block",
            "answer_mode",
            "time_limit_seconds",
            "correct_answer",
            "image",
            "video",
            "enable_paint",
        ]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "text"),
                }
            ),
            "block": forms.Select(
                attrs={
                    "class": "form-select bootstrap-single-select__native js-bootstrap-single-select",
                    "data-bootstrap-select": "",
                }
            ),
            "answer_mode": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "time_limit_seconds": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy(
                        "exams.form.question.placeholder",
                        "time_limit_seconds",
                    ),
                }
            ),
            "correct_answer": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "correct_answer"),
                }
            ),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "video": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "video/mp4,video/webm,video/quicktime",
                }
            ),
        }
        labels = {
            "text": pgettext_lazy("exams.form.question.label", "text"),
            "block": pgettext_lazy("exams.form.question.label", "block"),
            "answer_mode": pgettext_lazy("exams.form.question.label", "answer_mode"),
            "time_limit_seconds": pgettext_lazy("exams.form.question.label", "time_limit_seconds"),
            "correct_answer": pgettext_lazy("exams.form.question.label", "correct_answer"),
            "image": pgettext_lazy("exams.form.question.label", "image"),
            "video": pgettext_lazy("exams.form.question.label", "video"),
        }

    def __init__(self, *args, exam_type=None, subject_blocks=None, exam=None, **kwargs):
        """
        exam_type (test / written) view-dən ötürülür.
        """
        self.exam_type = exam_type
        self.exam = exam
        data = args[0] if args else None
        instance = kwargs.get("instance")
        self.option_indexes = self._resolve_option_indexes(data=data, instance=instance)
        super().__init__(*args, **kwargs)

        self._ensure_option_fields_exist()

        # Yazılı imtahanlarda enable_paint field-ini silmə
        if self.exam_type != "written":
            self.fields.pop("enable_paint", None)

        # Blokları dropdown-a doldururuq
        if subject_blocks is not None:
            self.fields["block"].queryset = subject_blocks
        else:
            self.fields["block"].queryset = QuestionBlock.objects.none()

        block_widget_attrs = self.fields["block"].widget.attrs
        block_widget_attrs["class"] = "form-select bootstrap-single-select__native js-bootstrap-single-select"
        block_widget_attrs["data-bootstrap-select"] = ""

        # Yazılı imtahanlarda answer_mode-u məcburi etməyək
        if self.exam_type == "written":
            self.fields["answer_mode"].required = False
            self.fields["block"].required = True
            self.fields["block"].empty_label = None
            block_widget_attrs["required"] = "required"
            block_widget_attrs["aria-required"] = "true"
            if "enable_paint" in self.fields and not self.is_bound:
                if instance and getattr(instance, "pk", None):
                    self.initial["enable_paint"] = instance.paint_enabled_effective
                elif self.exam is not None:
                    self.initial["enable_paint"] = bool(self.exam.enable_paint)
        else:
            self.fields["block"].empty_label = pgettext_lazy("exams.form.question.select", "block_empty")

        # Edit zamanı mövcud variantları inputlara doldur
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            options = list(instance.options.all().order_by("id"))
            for idx, opt in enumerate(options, start=1):
                self.fields[f"option{idx}_text"].initial = opt.text
                self.fields[f"option{idx}_is_correct"].initial = opt.is_correct

        self.option_fields = self._build_option_fields()

    def _resolve_option_indexes(self, *, data=None, instance=None):
        max_index = self.MIN_TEST_OPTIONS

        if data is not None:
            for key in data.keys():
                match = re.match(r"^option(\d+)_(text|is_correct)$", key)
                if match:
                    max_index = max(max_index, int(match.group(1)))
        elif instance is not None and getattr(instance, "pk", None):
            max_index = max(max_index, instance.options.count())

        return list(range(1, max_index + 1))

    def _option_label(self, index):
        suffix_map = {
            0: "cu",
            1: "ci",
            2: "ci",
            3: "cü",
            4: "cü",
            5: "ci",
            6: "cı",
            7: "ci",
            8: "ci",
            9: "cu",
        }
        suffix = suffix_map[index % 10]
        return f"{index}-{suffix} variant"

    def _ensure_option_fields_exist(self):
        for index in self.option_indexes:
            text_name = f"option{index}_text"
            correct_name = f"option{index}_is_correct"
            label = self._option_label(index)

            if text_name not in self.fields:
                self.fields[text_name] = forms.CharField(
                    label=label,
                    required=False,
                    widget=forms.TextInput(attrs={"class": "form-control"}),
                )
            else:
                self.fields[text_name].label = label

            if correct_name not in self.fields:
                self.fields[correct_name] = forms.BooleanField(
                    label=pgettext_lazy("exams.form.question.label", "option_correct"),
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                )

    def _build_option_fields(self):
        option_fields = []
        for index in self.option_indexes:
            option_fields.append(
                {
                    "index": index,
                    "label": self._option_label(index),
                    "text_field": self[f"option{index}_text"],
                    "is_correct_field": self[f"option{index}_is_correct"],
                }
            )
        return option_fields

    def _get_cleaned_options(self, cleaned_data):
        options = []
        for index in self.option_indexes:
            text = (cleaned_data.get(f"option{index}_text") or "").strip()
            is_correct = bool(cleaned_data.get(f"option{index}_is_correct"))
            if text:
                options.append(
                    {
                        "index": index,
                        "text": text,
                        "is_correct": is_correct,
                    }
                )
        return options

    def clean(self):
        cleaned_data = super().clean()
        answer_mode = cleaned_data.get("answer_mode")
        image = cleaned_data.get("image")
        video = cleaned_data.get("video")

        if image and not getattr(image, "_committed", False):
            validate_uploaded_file(
                image,
                allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
                max_size_mb=10,
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )
            randomize_uploaded_filename(image)

        if video and not getattr(video, "_committed", False):
            validate_uploaded_file(
                video,
                allowed_extensions={".mp4", ".webm", ".mov"},
                max_size_mb=30,
                allowed_mime_types={"video/mp4", "video/webm", "video/quicktime", "application/octet-stream"},
                allowed_mime_prefixes=("video/",),
            )
            randomize_uploaded_filename(video)

        # Yazılı imtahanda options validasiyasını skip edirik
        if self.exam_type == "written":
            if not cleaned_data.get("block"):
                self.add_error(
                    "block",
                    forms.ValidationError("Yazılı sual üçün mövzu bloku seçilməlidir."),
                )
            return cleaned_data

        # TEST üçün variant validasiyası
        opts = self._get_cleaned_options(cleaned_data)

        if answer_mode in ("single", "multiple") and not opts:
            raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "options_required"))

        if answer_mode in ("single", "multiple") and len(opts) < self.MIN_TEST_OPTIONS:
            raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "minimum_two_options"))

        if answer_mode == "single":
            correct_count = sum(1 for option in opts if option["is_correct"])
            if correct_count == 0:
                raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "single_requires_one_correct"))
            if correct_count > 1:
                raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "single_only_one_correct"))

        return cleaned_data

    def create_options(self, question_instance: ExamQuestion):
        """
        Yeni sual yaradılanda variantları yarat
        """
        for option in self._get_cleaned_options(self.cleaned_data):
            ExamQuestionOption.objects.create(
                question=question_instance,
                text=option["text"],
                is_correct=option["is_correct"],
            )

    def save_options(self, question_instance: ExamQuestion):
        """
        Edit zamanı köhnə variantları sil və yenilərini yarat
        """
        question_instance.options.all().delete()
        self.create_options(question_instance)
