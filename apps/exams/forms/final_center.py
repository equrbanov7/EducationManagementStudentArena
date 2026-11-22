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

    def clean_name(self):
        return " ".join((self.cleaned_data.get("name") or "").split())

    def clean_building(self):
        return " ".join((self.cleaned_data.get("building") or "").split())

    def clean(self):
        """Sahib 2026-11-23: eyni binada eyni adlı ikinci otaq yaradılmır (böyük/kiçik hərf fərq etmir).

        Redaktədə yoxlama yalnız ad və ya bina dəyişəndə işləyir — köhnə reyestrdə artıq olan cütlər
        (məs. köçürmədən qalan) başqa sahənin düzəlişini bloklamasın.
        """
        cleaned = super().clean()
        name = cleaned.get("name") or ""
        building = cleaned.get("building") or ""
        if not name:
            return cleaned
        if (
            self.instance.pk
            and name.lower() == (self.instance.name or "").strip().lower()
            and building == (self.instance.building or "").strip()
        ):
            return cleaned
        qs = ExamRoom.objects.filter(organization=self.organization, name__iexact=name, building=building)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(
                "name",
                pgettext_lazy("exams.final_center.form", "Bu binada bu adla otaq artıq var."),
            )
        return cleaned


__all__ = [
    "ExamRoomForm",
]
