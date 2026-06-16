"""Trial-exam request form.

Logged-in students submit their name, email, subject and a PDF of the
questions they want imported as a free practice exam. Name/email are
pre-filled from the authenticated user but stay editable (a student may
prefer a different contact address).

Validation
----------
* Name: 2–120 chars, no URLs (spam heuristic).
* Subject: 2–150 chars, required.
* Note: optional, max 2000 chars.
* File: required PDF, validated via ``core.upload_security`` (extension +
  real MIME signature + size). Anything but a genuine PDF is rejected.
* Honeypot: a hidden ``website`` field real users never fill.
"""

from __future__ import annotations

import re

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from core.upload_security import DEFAULT_MAX_UPLOAD_SIZE_MB, validate_uploaded_file

from .models import TrialExamRequest

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def _max_upload_mb() -> int:
    return int(getattr(settings, "TRIAL_EXAM_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_SIZE_MB))


class TrialExamRequestForm(forms.ModelForm):
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
        model = TrialExamRequest
        fields = ("full_name", "email", "subject_name", "note", "questions_file")
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "trial-form__input",
                    "placeholder": _("Adınız və soyadınız"),
                    "autocomplete": "name",
                    "maxlength": "120",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "trial-form__input",
                    "placeholder": "siz@example.com",
                    "autocomplete": "email",
                    "maxlength": "254",
                    "required": True,
                }
            ),
            "subject_name": forms.TextInput(
                attrs={
                    "class": "trial-form__input",
                    "placeholder": _("Məsələn: Riyaziyyat, İngilis dili, Tarix..."),
                    "maxlength": "150",
                    "required": True,
                }
            ),
            "note": forms.Textarea(
                attrs={
                    "class": "trial-form__input trial-form__textarea",
                    "placeholder": _("Əlavə qeyd (könüllü): sual sayı, çətinlik, istək..."),
                    "rows": 4,
                    "maxlength": "2000",
                }
            ),
            "questions_file": forms.ClearableFileInput(
                attrs={
                    "class": "trial-form__file-input",
                    "accept": "application/pdf,.pdf",
                    "required": True,
                }
            ),
        }

    # --- Field-level validators ---------------------------------------

    def clean_full_name(self) -> str:
        name = (self.cleaned_data.get("full_name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError(_("Ad ən azı 2 simvol olmalıdır."))
        if _URL_RE.search(name):
            raise forms.ValidationError(_("Ad daxilində link ola bilməz."))
        return name

    def clean_subject_name(self) -> str:
        subject = (self.cleaned_data.get("subject_name") or "").strip()
        if len(subject) < 2:
            raise forms.ValidationError(_("Fənnin adı ən azı 2 simvol olmalıdır."))
        if _URL_RE.search(subject):
            raise forms.ValidationError(_("Fənnin adında link ola bilməz."))
        return subject

    def clean_questions_file(self):
        uploaded = self.cleaned_data.get("questions_file")
        if not uploaded:
            raise forms.ValidationError(_("Zəhmət olmasa sualları PDF formatında yükləyin."))
        # Re-validate at form level so the error is shown inline (the model
        # validator only runs on full_clean / admin). Restricts to genuine PDFs.
        validate_uploaded_file(
            uploaded,
            allowed_extensions={".pdf"},
            allowed_mime_types={"application/pdf"},
            allowed_mime_prefixes=(),
            max_size_mb=_max_upload_mb(),
        )
        return uploaded

    def clean_website(self) -> str:
        # Honeypot: any non-empty value indicates a bot.
        value = (self.cleaned_data.get("website") or "").strip()
        if value:
            raise forms.ValidationError(_("Forma doğrulanmadı."))
        return ""
