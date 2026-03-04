from django import forms
from django.utils.translation import pgettext_lazy

from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from .models import Project, ProjectSubmission


class ProjectForm(forms.ModelForm):
    """Kurs işi forması"""

    class Meta:
        model = Project
        fields = [
            "title",
            "description",
            "start_date",
            "deadline",
            "max_attempts",
            "max_score",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("projects.form.project.placeholder", "title"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": pgettext_lazy("projects.form.project.placeholder", "description"),
                }
            ),
            "start_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "deadline": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "max_attempts": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 1}),
            "max_score": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 100}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "title": pgettext_lazy("projects.form.project.label", "title"),
            "description": pgettext_lazy("projects.form.project.label", "description"),
            "start_date": pgettext_lazy("projects.form.project.label", "start_date"),
            "deadline": pgettext_lazy("projects.form.project.label", "deadline"),
            "max_attempts": pgettext_lazy("projects.form.project.label", "max_attempts"),
            "max_score": pgettext_lazy("projects.form.project.label", "max_score"),
            "status": pgettext_lazy("projects.form.project.label", "status"),
        }


class ProjectSubmissionForm(forms.ModelForm):
    """Layihə təqdim etmə forması"""

    class Meta:
        model = ProjectSubmission
        fields = ["content", "file"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": pgettext_lazy("projects.form.submission.placeholder", "content"),
                    "required": True,
                }
            ),
            "file": forms.FileInput(attrs={"class": "form-control", "accept": ".zip,.pdf,.rar"}),
        }
        labels = {
            "content": pgettext_lazy("projects.form.submission.label", "content"),
            "file": pgettext_lazy("projects.form.submission.label", "file"),
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file

        validate_uploaded_file(
            file,
            allowed_extensions={
                ".zip",
                ".rar",
                ".7z",
                ".pdf",
                ".txt",
                ".doc",
                ".docx",
                ".png",
                ".jpg",
                ".jpeg",
            },
            max_size_mb=25,
        )
        randomize_uploaded_filename(file)
        return file


class GradeProjectSubmissionForm(forms.ModelForm):
    """Qiymətləndirmə forması"""

    class Meta:
        model = ProjectSubmission
        fields = ["grade", "feedback", "status"]
        widgets = {
            "grade": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": 0,
                    "max": 100,
                    "placeholder": pgettext_lazy("projects.form.grade.placeholder", "grade"),
                }
            ),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": pgettext_lazy("projects.form.grade.placeholder", "feedback"),
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "grade": pgettext_lazy("projects.form.grade.label", "grade"),
            "feedback": pgettext_lazy("projects.form.grade.label", "feedback"),
            "status": pgettext_lazy("projects.form.grade.label", "status"),
        }
