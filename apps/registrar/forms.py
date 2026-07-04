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

from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)


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


class OfferingForm(_OrgScopedModelForm):
    """Open a subject for a semester + group, with an instructor (semestr fənni)."""

    class Meta:
        model = CourseOffering
        fields = ["subject", "period", "group", "instructor", "lesson_hours", "is_active"]
        labels = {
            "subject": pgettext_lazy("registrar.console", "Fənn"),
            "period": pgettext_lazy("registrar.console", "Semestr (dövr)"),
            "group": pgettext_lazy("registrar.console", "Qrup (opsional)"),
            "instructor": pgettext_lazy("registrar.console", "Müəllim (opsional)"),
            "lesson_hours": pgettext_lazy("registrar.console", "Kontakt saatı"),
            "is_active": pgettext_lazy("registrar.console", "Aktiv"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.organization
        academic_period = django_apps.get_model("organizations", "AcademicPeriod")
        org_unit = django_apps.get_model("organizations", "OrgUnit")
        from django.contrib.auth import get_user_model

        user_model = get_user_model()

        self.fields["subject"].queryset = (
            Subject.objects.filter(organization=org, is_active=True).order_by("code") if org else Subject.objects.none()
        )
        self.fields["period"].queryset = (
            academic_period.objects.filter(organization=org).order_by("-start_date")
            if org
            else academic_period.objects.none()
        )
        group_field = self.fields["group"]
        group_field.required = False
        group_field.queryset = (
            org_unit.objects.filter(organization=org, unit_type="group").order_by("name")
            if org
            else org_unit.objects.none()
        )
        instructor_field = self.fields["instructor"]
        instructor_field.required = False
        instructor_field.queryset = (
            user_model.objects.filter(
                memberships__organization=org,
                memberships__role__name__in=["teacher", "assistant_teacher"],
                memberships__is_active=True,
            )
            .distinct()
            .order_by("username")
            if org
            else user_model.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get("subject")
        period = cleaned.get("period")
        group = cleaned.get("group")
        if subject and period:
            qs = CourseOffering.objects.filter(
                organization=self.organization, subject=subject, period=period, group=group
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    pgettext_lazy("registrar.console", "Bu fənn + semestr + qrup üçün fənn açılışı artıq var.")
                )
        return cleaned


class StudentRecordForm(_OrgScopedModelForm):
    """Assign a student to a program/curriculum/group (StudentAcademicRecord).

    Two extra, non-model fields let the registrar auto-enroll the student in the
    mandatory subjects of a semester right after assignment."""

    auto_enroll = forms.BooleanField(
        required=False, label=pgettext_lazy("registrar.console", "Cari semestrin məcburi fənlərinə yaz")
    )
    enroll_semester = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label=pgettext_lazy("registrar.console", "Semestr nömrəsi (auto-enroll)"),
    )

    class Meta:
        model = StudentAcademicRecord
        fields = ["student", "program", "curriculum", "group", "admission_year"]
        labels = {
            "student": pgettext_lazy("registrar.console", "Tələbə"),
            "program": pgettext_lazy("registrar.console", "İxtisas (proqram)"),
            "curriculum": pgettext_lazy("registrar.console", "Tədris planı"),
            "group": pgettext_lazy("registrar.console", "Qrup (opsional)"),
            "admission_year": pgettext_lazy("registrar.console", "Qəbul ili"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.organization
        org_unit = django_apps.get_model("organizations", "OrgUnit")
        from django.contrib.auth import get_user_model

        user_model = get_user_model()

        self.fields["student"].queryset = (
            user_model.objects.filter(
                memberships__organization=org,
                memberships__role__name__in=["student", "lead_student"],
                memberships__is_active=True,
            )
            .distinct()
            .order_by("username")
            if org
            else user_model.objects.none()
        )
        self.fields["program"].queryset = (
            Program.objects.filter(organization=org).order_by("name") if org else Program.objects.none()
        )
        self.fields["curriculum"].queryset = (
            Curriculum.objects.filter(organization=org).select_related("program").order_by("-admission_year")
            if org
            else Curriculum.objects.none()
        )
        group_field = self.fields["group"]
        group_field.required = False
        group_field.queryset = (
            org_unit.objects.filter(organization=org, unit_type="group").order_by("name")
            if org
            else org_unit.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        program = cleaned.get("program")
        curriculum = cleaned.get("curriculum")
        if curriculum and program and curriculum.program_id != program.id:
            self.add_error(
                "curriculum",
                pgettext_lazy("registrar.console", "Seçilən tədris planı bu ixtisasa aid deyil."),
            )
        if student and program:
            qs = StudentAcademicRecord.objects.filter(organization=self.organization, student=student, program=program)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    pgettext_lazy("registrar.console", "Bu tələbə həmin ixtisasa artıq təyin olunub.")
                )
        return cleaned
