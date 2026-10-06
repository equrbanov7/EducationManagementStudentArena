"""İdarə forması — BÜTÜN yoxlamalar server tərəfdədir (klientdəki seçicilər yalnız rahatlıqdır).

Auditoriya bölmələrinin əhatə yoxlaması ``services/access.validate_units``-dədir (menecerin
əhatəsi formaya ötürülür). «Müraciət et» konfiqurasiyası: daxili rejimdə növ bu təşkilatın
AKTİV növü olmalı və seçilmiş BÜTÜN ailələrə açıq olmalıdır; keçid rejimində yalnız
``http(s)://`` və ya eyni saytın ``/yol``-u (``//`` və ``javascript:`` rədd olunur).
"""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from django import forms
from django.utils.translation import pgettext, pgettext_lazy

from apps.applications.models import ApplicationKind, ApplicationUnit

from .constants import (
    APPLY_LABEL_MAX,
    BODY_MAX,
    FAMILY_TO_SENDER,
    MAX_TARGET_UNITS,
    SUMMARY_MAX,
    TITLE_MAX,
    URL_MAX,
    ApplyMode,
    Audience,
    Category,
    Priority,
)

_CTX = "announcements.manage"
_DT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]


def safe_apply_url(value: str) -> str | None:
    """Etibarlı keçid və ya ``None``: ``https://…`` / ``http://…`` və ya ``/yol`` (``//host`` yox)."""
    value = (value or "").strip()
    if not value or len(value) > URL_MAX or any(ch in value for ch in "\r\n\t\\ "):
        return None
    if value.startswith("/"):
        return value if not value.startswith("//") else None
    parts = urlsplit(value)
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return value
    return None


class AnnouncementForm(forms.Form):
    title = forms.CharField(max_length=TITLE_MAX, label=pgettext_lazy(_CTX, "Başlıq"))
    summary = forms.CharField(max_length=SUMMARY_MAX, required=False, label=pgettext_lazy(_CTX, "Qısa xülasə"))
    body = forms.CharField(
        max_length=BODY_MAX, required=False, widget=forms.Textarea, label=pgettext_lazy(_CTX, "Mətn")
    )
    category = forms.ChoiceField(choices=Category.choices, initial=Category.GENERAL)
    priority = forms.TypedChoiceField(choices=Priority.choices, coerce=int, initial=Priority.NORMAL)
    is_pinned = forms.BooleanField(required=False)
    show_as_popup = forms.BooleanField(required=False)
    publish_at = forms.DateTimeField(required=False, input_formats=_DT_FORMATS)
    expires_at = forms.DateTimeField(required=False, input_formats=_DT_FORMATS)
    deadline_at = forms.DateTimeField(required=False, input_formats=_DT_FORMATS)
    audience_families = forms.MultipleChoiceField(choices=Audience.choices)
    audience_units = forms.CharField(required=False)
    apply_mode = forms.ChoiceField(choices=ApplyMode.choices, initial=ApplyMode.NONE)
    apply_kind = forms.UUIDField(required=False)
    apply_unit = forms.UUIDField(required=False)
    apply_url = forms.CharField(max_length=URL_MAX, required=False)
    apply_label = forms.CharField(max_length=APPLY_LABEL_MAX, required=False)

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if len(value) < 3:
            raise forms.ValidationError(pgettext(_CTX, "Başlıq ən azı 3 simvol olmalıdır."))
        return value

    def clean_audience_units(self):
        raw = self.cleaned_data.get("audience_units") or ""
        values = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
        unique = list(dict.fromkeys(values))
        if len(unique) > MAX_TARGET_UNITS:
            raise forms.ValidationError(
                pgettext(_CTX, "Ən çox %(n)s bölmə seçmək olar.") % {"n": MAX_TARGET_UNITS}
            )
        for value in unique:
            try:
                uuid.UUID(value)
            except ValueError as exc:
                raise forms.ValidationError(pgettext(_CTX, "Bölmə seçimi yanlışdır.")) from exc
        return unique

    def _kind(self, pk):
        if not pk:
            return None
        return ApplicationKind.objects.filter(organization=self.organization, pk=pk, is_active=True).first()

    def clean(self):
        data = super().clean()
        publish_at, expires_at, deadline_at = data.get("publish_at"), data.get("expires_at"), data.get("deadline_at")
        if publish_at and expires_at and expires_at <= publish_at:
            self.add_error("expires_at", pgettext(_CTX, "Bitmə vaxtı dərc vaxtından sonra olmalıdır."))
        if deadline_at and publish_at and deadline_at <= publish_at:
            self.add_error("deadline_at", pgettext(_CTX, "Son tarix dərc vaxtından sonra olmalıdır."))
        mode = data.get("apply_mode")
        data["apply_kind_obj"] = data["apply_unit_obj"] = None
        if mode == ApplyMode.INTERNAL:
            kind = self._kind(data.get("apply_kind"))
            if kind is None:
                self.add_error("apply_kind", pgettext(_CTX, "Müraciət növünü seçin."))
            else:
                senders = {FAMILY_TO_SENDER[family] for family in data.get("audience_families") or []}
                missing = sorted(sender for sender in senders if not kind.allows(sender))
                if missing:
                    self.add_error(
                        "apply_kind",
                        pgettext(_CTX, "Bu müraciət növü seçilmiş auditoriyanın hamısına açıq deyil."),
                    )
                data["apply_kind_obj"] = kind
            unit_pk = data.get("apply_unit")
            if unit_pk:
                unit = ApplicationUnit.objects.filter(organization=self.organization, pk=unit_pk, is_active=True).first()
                if unit is None:
                    self.add_error("apply_unit", pgettext(_CTX, "Seçilmiş şöbə tapılmadı."))
                data["apply_unit_obj"] = unit
        elif mode == ApplyMode.URL:
            url = safe_apply_url(data.get("apply_url"))
            if url is None:
                self.add_error(
                    "apply_url",
                    pgettext(_CTX, "Keçid https:// ilə başlamalı və ya saytın daxili yolu (/…) olmalıdır."),
                )
            data["apply_url"] = url or ""
        return data


__all__ = ["AnnouncementForm", "safe_apply_url"]
