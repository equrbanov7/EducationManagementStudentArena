"""Locale-dən asılı OLMAYAN yalnız-tarix sahəsi: ``gg.aa.iiii`` (2026-11-14).

Niyə (sahib, 2026-11-14)
------------------------
«Bizdə Azərbaycanda standart tarix gün ay il olaraqdır.» Native ``<input type="date">`` brauzerin dilinə tabe idi
(en-US → ``mm/dd/yyyy``): müəllim jurnalın «Yeni dərs» modalında keçmiş tarixə dərs açmaq istəyəndə günü ay yerinə
yazırdı və «olmur» deyirdi.

Həll
----
Görünən sahə HƏMİŞƏ «gg.aa.iiii» + təqvim düyməsi (``EMSDateTime``, ``data-ems-dt-mode="date"``;
``static/js/ems_datetime.js`` + ``ems_datetime_picker.js``, üslub ``static/css/ems_datetime.css``). Forma dəyəri
(``name``) GİZLİ sahədə ISO «iiii-aa-gg» kimi gedir — server parserləri (``parse_date`` / ``date.fromisoformat``)
və həmin sahənin ``.value``-sunu oxuyub-yazan köhnə JS-lər dəyişmir. ``min`` / ``max`` aralığı wrapper-in
``data-ems-dt-min`` / ``data-ems-dt-max`` atributlarındadır: seçicidə kənar günlər bağlıdır, yazılanda mesaj aralığı
«gg.aa.iiii» ilə deyir. Şablonda: ``{% ems_date_input %}`` (``apps/accounts/templatetags/ems_ui.py``).
"""

from __future__ import annotations

import datetime
import json
import re

from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext

from core.datetime_input import CODE_INVALID, CODE_INVALID_DATE, DateTimeTextError, parse_datetime_text, picker_i18n

#: Tərcümə konteksti tarix-saat sahəsi ilə ORTAQdır (ortaq mətnlər — «Təqvimi aç», «Belə tarix yoxdur…» — bir dəfə).
_CTX = "core.datetime_input"

#: Yalnız-tarix göstəriş formatı (JS ``EMSDateTime.formatDate``).
DATE_DISPLAY_FORMAT = "%d.%m.%Y"

CODE_OUT_OF_RANGE = "out_of_range"
CODE_BEFORE_MIN = "before_min"
CODE_AFTER_MAX = "after_max"

#: Gizli ISO sahəsinə əlavə olunan qarmaq atributları (köhnə JS-lərin selektorları) — yalnız ``data-*``.
_HOOK_RE = re.compile(r"^data-[a-z0-9-]+$")


def as_date(value) -> datetime.date | None:
    """``date`` / ``datetime`` / ISO və ya gün-əvvəl mətn → ``date``; boş/oxunmayan → ``None``."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        parsed = parse_datetime_text(str(value), require_time=False)
    except DateTimeTextError:
        return None
    return parsed.date() if parsed is not None else None


def date_error_messages() -> dict[str, str]:
    """Yalnız-tarix sahəsinin mesajları; ``{min}`` / ``{max}`` JS-də «gg.aa.iiii» ilə əvəz olunur."""
    return {
        CODE_INVALID: pgettext(_CTX, "Tarixi gg.aa.iiii formatında yazın (məsələn, 06.10.2026)."),
        CODE_INVALID_DATE: pgettext(_CTX, "Belə tarix yoxdur. Günü, ayı və ili yoxlayın (gg.aa.iiii)."),
        CODE_OUT_OF_RANGE: pgettext(_CTX, "Tarix {min} ilə {max} arasında olmalıdır."),
        CODE_BEFORE_MIN: pgettext(_CTX, "Tarix {min} və ya daha sonra olmalıdır."),
        CODE_AFTER_MAX: pgettext(_CTX, "Tarix {max} və ya daha əvvəl olmalıdır."),
    }


def date_picker_i18n() -> dict:
    """Yalnız-tarix seçicisinin ``data-ems-dt-i18n`` JSON-u (saat mətnləri lazım deyil)."""
    data = picker_i18n()
    data.pop("hour", None)
    data.pop("minute", None)
    data["dialog"] = pgettext(_CTX, "Tarixi seçin")
    data["done"] = pgettext(_CTX, "Bağla")
    data["errors"] = date_error_messages()
    return data


def _hooks(iso_attrs: str):
    attrs = [attr for attr in (iso_attrs or "").split() if _HOOK_RE.match(attr)]
    # Yalnız regex-dən keçən ``data-*`` adları — istifadəçi mətni deyil, şablon sabitidir.
    return mark_safe("".join(f" {attr}" for attr in attrs))  # noqa: S308


def render_day_first_date_input(
    name: str,
    value=None,
    *,
    input_id: str,
    required: bool = False,
    min_value=None,
    max_value=None,
    css_class: str = "ems-input",
    iso_attrs: str = "",
    describedby: str = "",
):
    """«gg.aa.iiii» sahəsi + təqvim düyməsi + gizli ISO forma sahəsi (``name``).

    ``min_value`` / ``max_value`` — ``date`` və ya ISO (``None`` — hədsiz). ``iso_attrs`` — gizli sahəyə boşluqla
    ayrılmış ``data-*`` qarmaqları (məs. ``data-jd-lesson-date``). Wrapper ``<span>``-dır ki, ``<label>`` içində də
    düzgün HTML olsun; görünən sahənin ``id``-si ``<label for>`` üçündür.
    """
    day = as_date(value)
    low, high = as_date(min_value), as_date(max_value)
    return format_html(
        '<span class="ems-dt ems-dt--date" data-ems-dt data-ems-dt-mode="date"{}{} data-ems-dt-i18n="{}">'
        '<input type="text" id="{}" class="{} ems-dt__input" value="{}" placeholder="{}" inputmode="numeric" '
        'autocomplete="off" spellcheck="false" maxlength="10" data-ems-dt-input{}{}>'
        '<button type="button" class="ems-dt__toggle" data-ems-dt-toggle aria-haspopup="dialog" '
        'aria-expanded="false" aria-label="{}"><i class="fas fa-calendar-days" aria-hidden="true"></i></button>'
        '<input type="text" name="{}" value="{}" class="ems-dt__iso" hidden tabindex="-1" aria-hidden="true" '
        'autocomplete="off" data-ems-dt-iso{}></span>',
        format_html(' data-ems-dt-min="{}"', low.isoformat()) if low else "",
        format_html(' data-ems-dt-max="{}"', high.isoformat()) if high else "",
        json.dumps(date_picker_i18n(), ensure_ascii=False),
        input_id,
        css_class,
        day.strftime(DATE_DISPLAY_FORMAT) if day else "",
        pgettext(_CTX, "gg.aa.iiii"),
        mark_safe(" required") if required else "",
        format_html(' aria-describedby="{}"', describedby) if describedby else "",
        pgettext(_CTX, "Təqvimi aç"),
        name,
        day.isoformat() if day else "",
        _hooks(iso_attrs),
    )
