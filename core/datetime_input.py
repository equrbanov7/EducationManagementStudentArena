"""Locale-dən asılı OLMAYAN tarix-saat sahəsi: ``gg.aa.iiii ss:dd`` (24 saat).

Niyə (müəllim rəyi, 2026-10-08)
-------------------------------
İmtahan sehrbazındakı native ``<input type="datetime-local">`` brauzerin dilinə
tabe idi: en-US brauzerdə ``mm/dd/yyyy`` + boş AM/PM göstərirdi, «06/10» İYUN 10
kimi oxunurdu, əl ilə yazılan (yarımçıq) dəyər isə brauzer tərəfindən boş
göndərilirdi → «Başlama vaxtını seçin» xətası. Yalnız təqvim ikonu işləyirdi.

Həll — HƏMİŞƏ gün əvvəl, 24 saat
--------------------------------
* :class:`DayFirstDateTimeInput` — adi mətn sahəsi (``name`` dəyişmir) + təqvim
  düyməsi; seçici ``static/js/ems_datetime.js`` (``EMSDateTime``) ilə açılır,
  üslub ``static/css/ems_datetime.css``-dədir. Seçicinin mətnləri (ay/gün adları,
  xəta mesajları) ``data-ems-dt-i18n`` atributunda serverdən gəlir — JS kataloqu
  lazım deyil.
* :class:`DayFirstDateTimeField` — ``gg.aa.iiii ss:dd`` (ayırıcı ``.``, ``/``,
  ``-``; saatda ``:`` və ya ``.``; 2 rəqəmli il → 20ii) VƏ ISO 8601
  (``2026-10-06T09:30``, köhnə klientlər / API) qəbul edir. Naive dəyər CARİ
  zonada (``TIME_ZONE = Asia/Baku``) aware edilir.
* :func:`parse_datetime_text` — eyni qayda; JS əkizi ``EMSDateTime.parse``
  (paritet testi ``core/tests/test_datetime_input.py``).
"""

from __future__ import annotations

import datetime
import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms.utils import from_current_timezone
from django.utils.dateparse import parse_datetime
from django.utils.dates import MONTHS, WEEKDAYS, WEEKDAYS_ABBR
from django.utils.html import format_html
from django.utils.translation import pgettext, pgettext_lazy

#: Göstəriş/yazı formatı (strftime). JS ``EMSDateTime.format`` eyni çıxışı verir.
DISPLAY_FORMAT = "%d.%m.%Y %H:%M"

_TIME = r"(?:(?:\s+|\s*[T,]\s*)(\d{1,2})[:.](\d{2})(?::(\d{2})(?:\.\d+)?)?)?"
#: Gün əvvəl: 6.10.2026, 06/10/2026 9:30, 06-10-26 09.30 …
DAY_FIRST_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})" + _TIME + r"$", re.ASCII)
#: ISO (il əvvəl): 2026-10-06, 2026-10-06T09:30, 2026-10-06 09:30:00
ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})" + _TIME + r"$", re.ASCII)

CODE_INVALID = "invalid"
CODE_INVALID_DATE = "invalid_date"
CODE_INVALID_TIME = "invalid_time"
CODE_MISSING_TIME = "missing_time"

_CTX = "core.datetime_input"


class DateTimeTextError(ValueError):
    """Mətn tarix-saata çevrilmədi; ``code`` səbəbi bildirir (JS ilə eyni kodlar)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_datetime_text(text: str, *, require_time: bool = True) -> datetime.datetime | None:
    """``gg.aa.iiii ss:dd`` və ya ISO mətnini NAIVE ``datetime``-a çevirir.

    Boş mətn → ``None``. Uyğunsuzluqda :class:`DateTimeTextError` (kod:
    ``invalid`` / ``invalid_date`` / ``invalid_time`` / ``missing_time``).
    Saat ofsetli ISO (``…+04:00``, ``…Z``) Django ``parse_datetime`` ilə aware qaytarılır.
    """
    value = (text or "").strip()
    if not value:
        return None
    match = DAY_FIRST_RE.match(value)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
        year_num = int(year) + 2000 if len(year) == 2 else int(year)
    else:
        match = ISO_RE.match(value)
        if not match:
            try:
                aware = parse_datetime(value)
            except ValueError:
                aware = None
            if aware is None:
                raise DateTimeTextError(CODE_INVALID)
            return aware
        year_num, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour_text, minute_text, second_text = match.group(4), match.group(5), match.group(6)
    try:
        date = datetime.date(year_num, month, day)
    except ValueError as exc:
        raise DateTimeTextError(CODE_INVALID_DATE) from exc
    if hour_text is None:
        if require_time:
            raise DateTimeTextError(CODE_MISSING_TIME)
        return datetime.datetime(date.year, date.month, date.day)
    hour, minute, second = int(hour_text), int(minute_text), int(second_text or 0)
    if hour > 23 or minute > 59 or second > 59:
        raise DateTimeTextError(CODE_INVALID_TIME)
    return datetime.datetime(date.year, date.month, date.day, hour, minute, second)


def error_messages() -> dict[str, str]:
    """Server və klient üçün eyni (tərcümə olunan) xəta mətnləri."""
    return {
        CODE_INVALID: pgettext(_CTX, "Tarixi və saatı gg.aa.iiii ss:dd formatında yazın (məsələn, 06.10.2026 09:30)."),
        CODE_INVALID_DATE: pgettext(_CTX, "Belə tarix yoxdur. Günü, ayı və ili yoxlayın (gg.aa.iiii)."),
        CODE_INVALID_TIME: pgettext(_CTX, "Saat 00:00 ilə 23:59 arasında olmalıdır (24 saat formatı)."),
        CODE_MISSING_TIME: pgettext(_CTX, "Saatı da yazın (ss:dd, 24 saat formatı)."),
    }


def picker_i18n() -> dict:
    """Seçicinin bütün mətnləri — ``data-ems-dt-i18n`` JSON-u."""
    # Ay/gün adları Django-nun öz kataloqundandır (az/en/ru/tr hamısı var).
    # Həftə bazar ertəsindən başlayır (Azərbaycan təqvimi; WEEKDAYS[0] = bazar ertəsi).
    return {
        "months": [str(MONTHS[number]) for number in range(1, 13)],
        "weekdays": [str(WEEKDAYS_ABBR[number]) for number in range(7)],
        "weekdaysLong": [str(WEEKDAYS[number]) for number in range(7)],
        "dialog": pgettext(_CTX, "Tarix və saatı seçin"),
        "prevMonth": pgettext(_CTX, "Əvvəlki ay"),
        "nextMonth": pgettext(_CTX, "Növbəti ay"),
        "hour": pgettext(_CTX, "Saatı seçin"),
        "minute": pgettext(_CTX, "Dəqiqəni seçin"),
        "today": pgettext(_CTX, "Bu gün"),
        "done": pgettext(_CTX, "Hazırdır"),
        "errors": error_messages(),
    }


class DayFirstDateTimeInput(forms.DateTimeInput):
    """Mətn sahəsi + təqvim düyməsi; dəyər həmişə ``gg.aa.iiii ss:dd``."""

    input_type = "text"
    format = DISPLAY_FORMAT

    def __init__(self, attrs=None, format=None):  # noqa: A002 - Django imzası
        base = {
            "class": "form-control",
            "inputmode": "numeric",
            "autocomplete": "off",
            "spellcheck": "false",
            "maxlength": "19",
        }
        base.update(attrs or {})
        super().__init__(attrs=base, format=format or DISPLAY_FORMAT)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_attrs = context["widget"]["attrs"]
        widget_attrs.setdefault("placeholder", pgettext(_CTX, "gg.aa.iiii ss:dd"))
        widget_attrs["data-ems-dt-input"] = ""
        classes = widget_attrs.get("class", "").split()
        if "ems-dt__input" not in classes:
            classes.append("ems-dt__input")
        widget_attrs["class"] = " ".join(classes)
        if widget_attrs.get("id"):
            hint_id = f"{widget_attrs['id']}_hint"
            described = widget_attrs.get("aria-describedby", "").split()
            if hint_id not in described:
                described.append(hint_id)
            widget_attrs["aria-describedby"] = " ".join(described)
        return context

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        input_id = (attrs or {}).get("id") or self.attrs.get("id") or ""
        hint_id = f"{input_id}_hint" if input_id else ""
        return format_html(
            '<div class="ems-dt" data-ems-dt data-ems-dt-i18n="{}">{}'
            '<button type="button" class="ems-dt__toggle" data-ems-dt-toggle aria-haspopup="dialog" '
            'aria-expanded="false" aria-label="{}"><i class="fas fa-calendar-days" aria-hidden="true"></i>'
            "</button></div>"
            '<small class="form-text ems-dt__hint"{}>{}</small>',
            json.dumps(picker_i18n(), ensure_ascii=False),
            input_html,
            pgettext(_CTX, "Təqvimi aç"),
            format_html(' id="{}"', hint_id) if hint_id else "",
            pgettext(_CTX, "Format: gg.aa.iiii ss:dd (24 saat)"),
        )


class DayFirstDateTimeField(forms.DateTimeField):
    """``gg.aa.iiii ss:dd`` + ISO qəbul edən, CARİ zonada aware dəyər qaytaran sahə."""

    widget = DayFirstDateTimeInput
    default_error_messages = {
        CODE_INVALID: pgettext_lazy(
            _CTX, "Tarixi və saatı gg.aa.iiii ss:dd formatında yazın (məsələn, 06.10.2026 09:30)."
        ),
    }

    def __init__(self, *, require_time: bool = True, allow_iso_date_only: bool = False, **kwargs):
        self.require_time = require_time
        # Köhnə ISO yalnız-tarix («2026-10-06» → gecə yarısı) qəbul edən formalar üçün (məs. elanlar);
        # gün-əvvəl yazıda saat HƏMİŞƏ tələb olunur.
        self.allow_iso_date_only = allow_iso_date_only
        kwargs.setdefault("input_formats", [DISPLAY_FORMAT, "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"])
        super().__init__(**kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.datetime):
            return from_current_timezone(value)
        if isinstance(value, datetime.date):
            return from_current_timezone(datetime.datetime(value.year, value.month, value.day))
        text = str(value)
        try:
            parsed = parse_datetime_text(text, require_time=self.require_time)
        except DateTimeTextError as exc:
            if not (exc.code == CODE_MISSING_TIME and self.allow_iso_date_only and ISO_RE.match(text.strip())):
                raise ValidationError(error_messages()[exc.code], code=exc.code) from exc
            parsed = parse_datetime_text(text, require_time=False)
        if parsed is None:
            return None
        return from_current_timezone(parsed)
