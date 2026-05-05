import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext_lazy

from apps.exams.models import CodingExamQuestion, CodingTestCase

TEST_CASE_PLACEHOLDER = """[
  {"input": "2 3", "expected": "5", "points": 10}
]"""


def parse_test_cases(raw_value, *, visibility):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return []

    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValidationError(pgettext_lazy("exams.form.coding.error", "test_cases_must_be_json")) from exc

    if not isinstance(payload, list):
        raise ValidationError(pgettext_lazy("exams.form.coding.error", "test_cases_must_be_list"))

    parsed_cases = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValidationError(pgettext_lazy("exams.form.coding.error", "test_case_must_be_object"))

        input_data = str(item.get("input", ""))
        expected_output = str(item.get("expected", item.get("expected_output", "")))
        point_value = item.get("points", item.get("point_value", 1))

        try:
            point_value = int(point_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(pgettext_lazy("exams.form.coding.error", "test_case_points_must_be_integer")) from exc

        parsed_cases.append(
            {
                "input_data": input_data,
                "expected_output": expected_output,
                "point_value": max(point_value, 0),
                "visibility": visibility,
                "order": index,
            }
        )

    return parsed_cases


def dump_test_cases(cases):
    payload = [
        {
            "input": case.input_data,
            "expected": case.expected_output,
            "points": case.point_value,
        }
        for case in cases
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def sync_coding_test_cases(coding_question, *, visible_cases, hidden_cases):
    CodingTestCase.objects.filter(coding_question=coding_question).delete()
    test_cases = []
    order = 1
    for case in [*visible_cases, *hidden_cases]:
        test_cases.append(
            CodingTestCase(
                coding_question=coding_question,
                input_data=case["input_data"],
                expected_output=case["expected_output"],
                visibility=case["visibility"],
                point_value=case["point_value"],
                order=order,
            )
        )
        order += 1
    if test_cases:
        CodingTestCase.objects.bulk_create(test_cases)


class CodingExamQuestionForm(forms.ModelForm):
    visible_test_cases = forms.CharField(
        label=pgettext_lazy("exams.form.coding.label", "visible_test_cases"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control coding-testcase-json",
                "rows": 6,
                "placeholder": TEST_CASE_PLACEHOLDER,
            }
        ),
        help_text=pgettext_lazy("exams.form.coding.help", "visible_test_cases"),
    )
    hidden_test_cases = forms.CharField(
        label=pgettext_lazy("exams.form.coding.label", "hidden_test_cases"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control coding-testcase-json",
                "rows": 6,
                "placeholder": TEST_CASE_PLACEHOLDER,
            }
        ),
        help_text=pgettext_lazy("exams.form.coding.help", "hidden_test_cases"),
    )

    class Meta:
        model = CodingExamQuestion
        fields = [
            "language",
            "title",
            "problem_statement",
            "input_description",
            "output_description",
            "example_input",
            "example_output",
            "time_limit_seconds",
            "memory_limit_mb",
            "max_score",
            "starter_code",
            "allow_file_creation",
            "allow_multiple_files",
            "enable_code_execution",
        ]
        widgets = {
            "language": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "problem_statement": forms.Textarea(attrs={"class": "form-control", "rows": 7}),
            "input_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "output_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "example_input": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "example_output": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "time_limit_seconds": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "memory_limit_mb": forms.NumberInput(attrs={"class": "form-control", "min": "16"}),
            "max_score": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "starter_code": forms.Textarea(attrs={"class": "form-control code-textarea", "rows": 10}),
            "allow_file_creation": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_multiple_files": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "enable_code_execution": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "language": pgettext_lazy("exams.form.coding.label", "language"),
            "title": pgettext_lazy("exams.form.coding.label", "title"),
            "problem_statement": pgettext_lazy("exams.form.coding.label", "problem_statement"),
            "input_description": pgettext_lazy("exams.form.coding.label", "input_description"),
            "output_description": pgettext_lazy("exams.form.coding.label", "output_description"),
            "example_input": pgettext_lazy("exams.form.coding.label", "example_input"),
            "example_output": pgettext_lazy("exams.form.coding.label", "example_output"),
            "time_limit_seconds": pgettext_lazy("exams.form.coding.label", "time_limit"),
            "memory_limit_mb": pgettext_lazy("exams.form.coding.label", "memory_limit"),
            "max_score": pgettext_lazy("exams.form.coding.label", "maximum_score"),
            "starter_code": pgettext_lazy("exams.form.coding.label", "starter_code"),
            "allow_file_creation": pgettext_lazy("exams.form.coding.label", "allow_file_creation"),
            "allow_multiple_files": pgettext_lazy("exams.form.coding.label", "allow_multiple_files"),
            "enable_code_execution": pgettext_lazy("exams.form.coding.label", "enable_code_execution"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            visible_cases = self.instance.test_cases.filter(visibility=CodingTestCase.VISIBILITY_VISIBLE)
            hidden_cases = self.instance.test_cases.filter(visibility=CodingTestCase.VISIBILITY_HIDDEN)
            self.initial["visible_test_cases"] = dump_test_cases(visible_cases)
            self.initial["hidden_test_cases"] = dump_test_cases(hidden_cases)

    def clean_visible_test_cases(self):
        return parse_test_cases(
            self.cleaned_data.get("visible_test_cases"),
            visibility=CodingTestCase.VISIBILITY_VISIBLE,
        )

    def clean_hidden_test_cases(self):
        return parse_test_cases(
            self.cleaned_data.get("hidden_test_cases"),
            visibility=CodingTestCase.VISIBILITY_HIDDEN,
        )

    def save_test_cases(self, coding_question):
        sync_coding_test_cases(
            coding_question,
            visible_cases=self.cleaned_data.get("visible_test_cases") or [],
            hidden_cases=self.cleaned_data.get("hidden_test_cases") or [],
        )
