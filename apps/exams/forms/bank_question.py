"""
Müstəqil sual bankı (BankQuestion) üçün tək-sual forması.

``ExamQuestionCreateForm`` ilə eyni dinamik variant mexanizmini istifadə edir ki,
``question_form.js`` (window.ExamQuestionForm) dəyişiksiz işləsin. Fərq: blok/vaxt/
paint sahələri yoxdur; əvəzinə bank üçün çətinlik, dil, bal sahələri var.
"""

import re

from django import forms
from django.utils.translation import pgettext_lazy

from apps.exams.constants import EXAM_LANGUAGE_CHOICES
from apps.exams.models import BankQuestion, BankQuestionOption
from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file


class BankQuestionCreateForm(forms.ModelForm):
    """Bank sualı yaratmaq/redaktə etmək — test (variantlı) və yazılı (sərbəst)."""

    MIN_TEST_OPTIONS = 2

    class Meta:
        model = BankQuestion
        fields = ["text", "correct_answer", "difficulty", "language", "points", "image", "video"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "text"),
                }
            ),
            "correct_answer": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "correct_answer"),
                }
            ),
            "difficulty": forms.Select(
                attrs={
                    "class": "form-select bootstrap-single-select__native js-bootstrap-single-select",
                    "data-bootstrap-select": "",
                }
            ),
            "language": forms.Select(
                attrs={
                    "class": "form-select bootstrap-single-select__native js-bootstrap-single-select",
                    "data-bootstrap-select": "",
                }
            ),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "video": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "video/mp4,video/webm,video/quicktime"}
            ),
        }
        labels = {
            "text": pgettext_lazy("exams.form.question.label", "text"),
            "correct_answer": pgettext_lazy("exams.form.question.label", "correct_answer"),
            "difficulty": pgettext_lazy("exams.form.bank_question.label", "difficulty"),
            "language": pgettext_lazy("exams.form.bank_question.label", "language"),
            "points": pgettext_lazy("exams.form.bank_question.label", "points"),
            "image": pgettext_lazy("exams.form.question.label", "image"),
            "video": pgettext_lazy("exams.form.question.label", "video"),
        }

    def __init__(self, *args, question_type="test", default_language=None, **kwargs):
        self.question_type = question_type if question_type in ("test", "written") else "test"
        data = args[0] if args else None
        instance = kwargs.get("instance")
        self.option_indexes = self._resolve_option_indexes(data=data, instance=instance)
        super().__init__(*args, **kwargs)

        self.fields["language"].choices = EXAM_LANGUAGE_CHOICES
        if default_language and not self.is_bound and not (instance and instance.pk):
            self.initial["language"] = default_language

        # Yazılı formatda variant sahələri lazım deyil; test formatda correct_answer lazım deyil.
        if self.question_type == "written":
            self.fields.pop("image", None)
            self.fields.pop("video", None)
        else:
            self.fields["correct_answer"].required = False
            self._ensure_option_fields_exist()
            instance = getattr(self, "instance", None)
            if instance and instance.pk:
                options = list(instance.options.all().order_by("label", "id"))
                for idx, opt in enumerate(options, start=1):
                    if f"option{idx}_text" in self.fields:
                        self.fields[f"option{idx}_text"].initial = opt.text
                        self.fields[f"option{idx}_is_correct"].initial = opt.is_correct
            self.option_fields = self._build_option_fields()

    # ---- Variant mexanizmi (ExamQuestionCreateForm ilə eyni) ----
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
        return f"{index}. variant"

    def _ensure_option_fields_exist(self):
        for index in self.option_indexes:
            text_name = f"option{index}_text"
            correct_name = f"option{index}_is_correct"
            if text_name not in self.fields:
                self.fields[text_name] = forms.CharField(
                    label=self._option_label(index),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "form-control"}),
                )
            if correct_name not in self.fields:
                self.fields[correct_name] = forms.BooleanField(
                    label=pgettext_lazy("exams.form.question.label", "option_correct"),
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
                )

    def _build_option_fields(self):
        return [
            {
                "index": index,
                "label": self._option_label(index),
                "text_field": self[f"option{index}_text"],
                "is_correct_field": self[f"option{index}_is_correct"],
            }
            for index in self.option_indexes
        ]

    def _get_cleaned_options(self, cleaned_data):
        options = []
        for index in self.option_indexes:
            text = (cleaned_data.get(f"option{index}_text") or "").strip()
            if text:
                options.append(
                    {"index": index, "text": text, "is_correct": bool(cleaned_data.get(f"option{index}_is_correct"))}
                )
        return options

    def clean(self):
        cleaned_data = super().clean()
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

        if self.question_type == "written":
            return cleaned_data

        opts = self._get_cleaned_options(cleaned_data)
        if len(opts) < self.MIN_TEST_OPTIONS:
            raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "minimum_two_options"))
        correct_count = sum(1 for option in opts if option["is_correct"])
        if correct_count == 0:
            raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "single_requires_one_correct"))
        cleaned_data["answer_mode"] = "multiple" if correct_count > 1 else "single"
        return cleaned_data

    def create_options(self, question_instance):
        labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for position, option in enumerate(self._get_cleaned_options(self.cleaned_data)):
            BankQuestionOption.objects.create(
                question=question_instance,
                label=labels[position] if position < len(labels) else None,
                text=option["text"],
                is_correct=option["is_correct"],
            )

    def save_options(self, question_instance):
        question_instance.options.all().delete()
        self.create_options(question_instance)
