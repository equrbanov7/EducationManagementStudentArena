"""Coding exam fields mixed into the teacher-facing ExamForm."""

from django import forms
from django.utils.translation import pgettext_lazy

from apps.exams.models import CodingExamQuestion

from .coding import TEST_CASE_PLACEHOLDER


class CodingExamFieldsMixin(forms.Form):
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
