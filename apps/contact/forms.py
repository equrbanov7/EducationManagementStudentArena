"""Contact form with strict validation and basic anti-spam protection.

Validation rules
----------------
* Name: 2–120 chars, no URLs (common spam pattern).
* Email: standard EmailField + length cap.
* Phone: optional, max 32 chars, only digits / +/-/space/parentheses.
* Subject: must be one of the model's SUBJECT_CHOICES.
* Message: 10–5000 chars, no more than 3 URLs (anti-spam heuristic).
* Honeypot: a hidden `website` field that real users won't fill in;
  bots typically auto-fill every input.
"""

from __future__ import annotations

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ContactMessage

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,32}$")


class ContactForm(forms.ModelForm):
    # Honeypot — must remain empty. Hidden via CSS in the template.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "aria-hidden": "true",
            }
        ),
    )

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "ems-contact__input",
                    "placeholder": _("Adınız və soyadınız"),
                    "autocomplete": "name",
                    "maxlength": "120",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "ems-contact__input",
                    "placeholder": "siz@example.com",
                    "autocomplete": "email",
                    "maxlength": "254",
                    "required": True,
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "ems-contact__input",
                    "placeholder": "+994 ...",
                    "autocomplete": "tel",
                    "maxlength": "32",
                }
            ),
            "subject": forms.Select(attrs={"class": "ems-contact__input ems-contact__select"}),
            "message": forms.Textarea(
                attrs={
                    "class": "ems-contact__input ems-contact__textarea",
                    "placeholder": _("Mesajınızı yazın..."),
                    "rows": 6,
                    "maxlength": "5000",
                    "required": True,
                }
            ),
        }

    # --- Field-level validators ---------------------------------------

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError(_("Ad ən azı 2 simvol olmalıdır."))
        if _URL_RE.search(name):
            raise forms.ValidationError(_("Ad daxilində link ola bilməz."))
        return name

    def clean_phone(self) -> str:
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and not _PHONE_RE.match(phone):
            raise forms.ValidationError(
                _("Telefon nömrəsi yalnız rəqəm və +, -, (, ) simvollarından ibarət ola bilər.")
            )
        return phone

    def clean_message(self) -> str:
        message = (self.cleaned_data.get("message") or "").strip()
        if len(message) < 10:
            raise forms.ValidationError(_("Mesaj ən azı 10 simvol olmalıdır."))
        if len(_URL_RE.findall(message)) > 3:
            raise forms.ValidationError(_("Mesajda çox sayda link aşkar edildi."))
        return message

    def clean_website(self) -> str:
        # Honeypot: any non-empty value indicates a bot.
        value = (self.cleaned_data.get("website") or "").strip()
        if value:
            raise forms.ValidationError(_("Forma doğrulanmadı."))
        return ""
