"""Telefon sahəsi komponenti: ölkə seçicisi (bayraq + ad + zəng kodu) + yerli nömrə xanası (sahib 2026-10-25).

İstifadə::

    {% load phone_tags %}
    {% phone_field name="phone" value=profile.phone field_id="phone" input_class="form-control" %}

Forma ``<name>_country`` (ISO-2, defolt AZ) və ``<name>`` (yerli nömrə) göndərir; server tərəfi
``core.phone.clean_phone_field`` ilə yoxlayıb E.164-ə gətirir. Saxlanmış nömrənin ölkəsi nömrədən tanınır.
Xəta ilə yenidən göstərəndə ``value`` = istifadəçinin yazdığı mətn, ``country`` = seçdiyi ölkədir.
JS: ``static/js/phone_field.js`` (placeholder, ``+kod`` yapışdırılanda ölkənin avtomatik seçilməsi).
"""

from __future__ import annotations

from django import template

from core import phone as phone_lib

register = template.Library()


@register.inclusion_tag("partials/_phone_field.html")
def phone_field(
    name="phone",
    value="",
    country="",
    field_id="",
    input_class="",
    css_class="",
    required=False,
    autofocus=False,
    invalid=False,
    describedby="",
    data_attr="",
    aria_label="",
):
    if country:
        region = phone_lib.normalize_region(country)
        national = str(value or "")
    else:
        parts = phone_lib.split_phone(value)
        region, national = parts.region, parts.national
    return {
        "name": name,
        "field_id": field_id or f"id_{name}",
        "iso": region,
        "national": national,
        "placeholder": phone_lib.example_national(region),
        "options": phone_lib.country_options(),
        "input_class": input_class,
        "css_class": css_class,
        "required": bool(required),
        "autofocus": bool(autofocus),
        "invalid": bool(invalid),
        "describedby": describedby,
        "data_attr": data_attr,
        "aria_label": aria_label,
    }
