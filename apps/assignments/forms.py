from django import forms
from django.utils.translation import pgettext_lazy

from .models import Assignment, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    """Sərbəst iş forması"""

    class Meta:
        model = Assignment
        fields = ["title", "description", "start_date", "due_date", "max_attempts", "status"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "title"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "description"),
                }
            ),
            "start_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "max_attempts": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "title": pgettext_lazy("assignment.form.label", "title"),
            "description": pgettext_lazy("assignment.form.label", "description"),
            "start_date": pgettext_lazy("assignment.form.label", "start_date"),
            "due_date": pgettext_lazy("assignment.form.label", "due_date"),
            "max_attempts": pgettext_lazy("assignment.form.label", "max_attempts"),
            "status": pgettext_lazy("assignment.form.label", "status"),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    """Cavab göndərmə forması"""

    class Meta:
        model = AssignmentSubmission
        fields = ["content", "file"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "submission_content"),
                    "required": True,
                }
            ),
            "file": forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.doc,.docx,.txt,.zip"}),
        }
        labels = {
            "content": pgettext_lazy("assignment.form.label", "submission_content"),
            "file": pgettext_lazy("assignment.form.label", "submission_file_optional"),
        }


class GradeSubmissionForm(forms.ModelForm):
    """Qiymətləndirmə forması"""

    class Meta:
        model = AssignmentSubmission
        fields = ["grade", "feedback", "status"]
        widgets = {
            "grade": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": 0,
                    "max": 100,
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "grade_range"),
                }
            ),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "feedback"),
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "grade": pgettext_lazy("assignment.form.label", "grade"),
            "feedback": pgettext_lazy("assignment.form.label", "feedback"),
            "status": pgettext_lazy("assignment.form.label", "status"),
        }
