"""Public contact channels for the current organization or branded deployment."""

from django.conf import settings
from django.core.exceptions import ValidationError

import phonenumbers

from core.phone import clean_phone, display_phone


def whatsapp_channel(request):
    org_settings = getattr(getattr(request, "organization", None), "settings", None)
    contact = org_settings.get("contact") if isinstance(org_settings, dict) else None
    number = getattr(settings, "CONTACT_WHATSAPP_NUMBER", "")
    if isinstance(contact, dict):
        number = contact.get("whatsapp_number", number)
    try:
        e164 = clean_phone(number)
    except ValidationError:
        return None
    if not e164 or not phonenumbers.is_valid_number(phonenumbers.parse(e164, None)):
        return None
    return {"url": f"https://wa.me/{e164[1:]}", "label": display_phone(e164)}
