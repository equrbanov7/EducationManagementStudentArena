"""Registrar console forms (K3) — web management of the academic catalogue.

``ProgramForm`` / ``SubjectForm`` are tenant-aware: the caller passes the active
``organization`` so the per-org unique ``code`` constraint is validated with a
friendly message (instead of an IntegrityError) and the optional specialty-unit
choices are scoped to that organization. ``organization`` itself is never a form
field — the view sets it on save so a client can't cross tenants.
"""

from __future__ import annotations

from django import forms
from django.apps import apps as django_apps
from django.utils.translation import pgettext_lazy

from apps.registrar.models import Curriculum, CurriculumSubject, Program, Subject


class _OrgScopedModelForm(forms.ModelForm):
    """A ModelForm bound to an organization for scoped validation."""

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def _code_is_taken(self, model, code) -> bool:
        qs = model.objects.filter(organization=self.organization, code__iexact=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.exists()


class ProgramForm(_OrgScopedModelForm):
    class Meta:
        model = Program
        fields = ["code", "name", "degree_level", "specialty_unit", "ects_total", "absence_limit_percent", "is_active"]
        widgets = {
            "code": forms.TextInput(attrs={"maxlength": 32}),
            "name": forms.TextInput(attrs={"maxlength": 255}),
        }
        labels = {
            "code": pgettext_lazy("registrar.console", "Kod"),
            "name": pgettext_lazy("registrar.console", "Ad"),
            "degree_level": pgettext_lazy("registrar.console", "Təhsil pilləsi"),
            "specialty_unit": pgettext_lazy("registrar.console", "İxtisas bölməsi (opsional)"),
            "ects_total": pgettext_lazy("registrar.console", "Məzuniyyət ECTS yükü"),
            "absence_limit_percent": pgettext_lazy("registrar.console", "Qayıb limiti (%)"),
            "is_active": pgettext_lazy("registrar.console", "Aktiv"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the specialty-unit choices to the org's specialty OrgUnits.
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        field = self.fields.get("specialty_unit")
        if field is not None:
            field.required = False
            if self.organization is not None:
                field.queryset = OrgUnit.objects.filter(organization=self.organization, unit_type="specialty").order_by(
                    "name"
                )
            else:
                field.queryset = OrgUnit.objects.none()

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if code and self._code_is_taken(Program, code):
            raise forms.ValidationError(pgettext_lazy("registrar.console", "Bu proqram kodu artıq mövcuddur."))
        return code


class SubjectForm(_OrgScopedModelForm):
    class Meta:
        model = Subject
        fields = ["code", "name", "ects", "description", "is_active"]
        widgets = {
            "code": forms.TextInput(attrs={"maxlength": 32}),
            "name": forms.TextInput(attrs={"maxlength": 255}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "code": pgettext_lazy("registrar.console", "Kod"),
            "name": pgettext_lazy("registrar.console", "Ad"),
            "ects": pgettext_lazy("registrar.console", "ECTS krediti"),
            "description": pgettext_lazy("registrar.console", "Təsvir"),
            "is_active": pgettext_lazy("registrar.console", "Aktiv"),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if code and self._code_is_taken(Subject, code):
            raise forms.ValidationError(pgettext_lazy("registrar.console", "Bu fənn kodu artıq mövcuddur."))
        return code


class CurriculumForm(_OrgScopedModelForm):
    class Meta:
        model = Curriculum
        fields = ["program", "admission_year", "name", "is_active"]
        widgets = {"name": forms.TextInput(attrs={"maxlength": 255})}
        labels = {
            "program": pgettext_lazy("registrar.console", "İxtisas (proqram)"),
            "admission_year": pgettext_lazy("registrar.console", "Qəbul ili"),
            "name": pgettext_lazy("registrar.console", "Ad (opsional)"),
            "is_active": pgettext_lazy("registrar.console", "Aktiv"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["program"]
        field.queryset = (
            Program.objects.filter(organization=self.organization).order_by("name")
            if self.organization is not None
            else Program.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get("program")
        year = cleaned.get("admission_year")
        if program and year:
            qs = Curriculum.objects.filter(organization=self.organization, program=program, admission_year=year)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    pgettext_lazy("registrar.console", "Bu proqram + qəbul ili üçün tədris planı artıq var.")
                )
        return cleaned


class CurriculumSubjectForm(forms.ModelForm):
    """A plan row. Bound to a curriculum (for the org + duplicate check)."""

    class Meta:
        model = CurriculumSubject
        fields = ["subject", "semester_number", "is_elective", "elective_group", "required_choices"]
        labels = {
            "subject": pgettext_lazy("registrar.console", "Fənn"),
            "semester_number": pgettext_lazy("registrar.console", "Semestr"),
            "is_elective": pgettext_lazy("registrar.console", "Seçmə fənn"),
            "elective_group": pgettext_lazy("registrar.console", "Seçmə blok adı"),
            "required_choices": pgettext_lazy("registrar.console", "Seçim sayı"),
        }

    def __init__(self, *args, curriculum=None, **kwargs):
        self.curriculum = curriculum
        super().__init__(*args, **kwargs)
        org = getattr(curriculum, "organization_id", None)
        self.fields["subject"].queryset = (
            Subject.objects.filter(organization_id=org, is_active=True).order_by("code")
            if org
            else Subject.objects.none()
        )
        self.fields["elective_group"].required = False

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get("subject")
        semester = cleaned.get("semester_number")
        if subject and semester and self.curriculum is not None:
            exists = CurriculumSubject.objects.filter(
                organization=self.curriculum.organization,
                curriculum=self.curriculum,
                subject=subject,
                semester_number=semester,
            ).exists()
            if exists:
                raise forms.ValidationError(
                    pgettext_lazy("registrar.console", "Bu fənn həmin semestrdə plana artıq əlavə olunub.")
                )
        return cleaned
