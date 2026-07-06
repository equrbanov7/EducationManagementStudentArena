"""Final imtahan mərkəzi formaları — zal və oturum idarəsi."""

from django import forms
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.exams.models import Exam, ExamRoom, ExamRoomSession, StudentGroup


class ExamRoomForm(forms.ModelForm):
    """Zal yaratma/redaktə. ``organization`` view qatında təyin olunur."""

    class Meta:
        model = ExamRoom
        fields = ["name", "code", "building", "floor", "capacity", "computer_count", "notes", "is_active"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        qs = ExamRoom.objects.filter(organization=self.organization, code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(pgettext_lazy("exams.final_center.form", "Bu kod ilə zal artıq mövcuddur."))
        return code


class ExamRoomSessionForm(forms.ModelForm):
    """
    Oturum yaratma. Yalnız FINAL kateqoriyalı, aktiv imtahanlar seçilə bilər;
    zal/nəzarətçi seçimləri org-scoped olur (view ötürür).
    """

    class Meta:
        model = ExamRoomSession
        fields = ["exam", "room", "invigilator", "staff", "scheduled_start", "scheduled_end", "notes"]
        widgets = {
            "scheduled_start": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "scheduled_end": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, organization=None, staff_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["exam"].queryset = Exam.objects.filter(
            organization=organization, exam_type_extended="final", is_archived=False
        ).order_by("-created_at")
        self.fields["room"].queryset = ExamRoom.objects.filter(organization=organization, is_active=True)
        if staff_queryset is not None:
            self.fields["invigilator"].queryset = staff_queryset
            self.fields["staff"].queryset = staff_queryset
        self.fields["staff"].required = False
        self.fields["invigilator"].required = False
        for field_name in ("scheduled_start", "scheduled_end"):
            self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("scheduled_start"), cleaned.get("scheduled_end")
        if start and end and end <= start:
            self.add_error(
                "scheduled_end",
                pgettext_lazy("exams.final_center.form", "Bitmə vaxtı başlama vaxtından sonra olmalıdır."),
            )
        if start and not self.instance.pk and start < timezone.now() - timezone.timedelta(hours=1):
            self.add_error(
                "scheduled_start", pgettext_lazy("exams.final_center.form", "Başlama vaxtı keçmişdə ola bilməz.")
            )
        return cleaned


class AssignStudentsForm(forms.Form):
    """Oturuma tələbə təyinatı: qrupdan və/və ya istifadəçi adları siyahısından."""

    group = forms.ModelChoiceField(
        queryset=StudentGroup.objects.none(),
        required=False,
        label=pgettext_lazy("exams.final_center.form", "Tələbə qrupu"),
    )
    usernames = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "username1, username2 …"}),
        label=pgettext_lazy("exams.final_center.form", "İstifadəçi adları"),
        help_text=pgettext_lazy("exams.final_center.form", "Vergül və ya yeni sətirlə ayrılmış istifadəçi adları."),
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = StudentGroup.objects.filter(organization=organization).order_by("name")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("group") and not (cleaned.get("usernames") or "").strip():
            raise forms.ValidationError(
                pgettext_lazy("exams.final_center.form", "Qrup seçin və ya istifadəçi adlarını daxil edin.")
            )
        return cleaned

    def username_list(self):
        raw = self.cleaned_data.get("usernames") or ""
        parts = [p.strip() for chunk in raw.splitlines() for p in chunk.split(",")]
        return [p for p in parts if p]


__all__ = [
    "AssignStudentsForm",
    "ExamRoomForm",
    "ExamRoomSessionForm",
]
