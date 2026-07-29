"""Final imtahan mərkəzi formaları — zal və oturum idarəsi."""

from django import forms
from django.utils.translation import pgettext_lazy

from apps.exams.models import ExamRoom


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


__all__ = [
    "ExamRoomForm",
]
