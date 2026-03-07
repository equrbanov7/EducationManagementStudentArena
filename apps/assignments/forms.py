from django import forms
from django.utils.translation import pgettext_lazy

from .models import Assignment, AssignmentSubmission
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file


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

    file = forms.FileField(
        required=False,
        label=pgettext_lazy("assignment.form.label", "submission_file_optional"),
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.doc,.docx,.txt,.zip"}),
    )

    class Meta:
        model = AssignmentSubmission
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": pgettext_lazy("assignment.form.placeholder", "submission_content"),
                    "required": True,
                }
            )
        }
        labels = {
            "content": pgettext_lazy("assignment.form.label", "submission_content"),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file is None:
            self._original_file_name = ""
            return None

        validate_uploaded_file(
            uploaded_file,
            allowed_extensions={".zip", ".rar", ".7z", ".pdf", ".txt", ".doc", ".docx", ".png", ".jpg", ".jpeg"},
            max_size_mb=25,
        )
        self._original_file_name = uploaded_file.name
        return randomize_uploaded_filename(uploaded_file)

    def save(self, commit=True):
        submission = super().save(commit=commit)
        uploaded_file = self.cleaned_data.get("file")
        if commit and uploaded_file is not None:
            submission.attach_uploaded_file(uploaded_file, original_name=getattr(self, "_original_file_name", ""))
            submission.save(update_fields=["files"])
        return submission


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
