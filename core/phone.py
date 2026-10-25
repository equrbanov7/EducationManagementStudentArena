"""Beynəlxalq telefon nömrəsi — ölkə seçimi, E.164 saxlama, ölkəyə uyğun yoxlama (sahib 2026-10-25).

Sahib: «Daxil olarkən telefon nömrəsi istəyirik, xarici vətəndaşlar var. Ölkə seçəndə ölkəyə uyğun prefikslər
çıxsın; default AZE-dir, amma istəsə kimsə dəyişə bilsin.»

Bu modul YEGANƏ mənbədir: ölkə siyahısı (ad + zəng kodu + nümunə), nömrənin ölkəyə görə yoxlanması və E.164
(``+<kod><nömrə>``) şəklinə gətirilməsi, saxlanmış nömrənin (ölkə, yerli nömrə) cütünə ayrılması. Forma
komponenti (``apps/accounts/templatetags/phone_tags.py`` + ``static/js/phone_field.js``) və hər yazma yolu
(məcburi profil tamamlama, profil redaktəsi, RİM yaratma / redaktə, əlaqə forması) buradan oxuyur.

QAYDALAR

* Yoxlama ``phonenumbers`` (libphonenumber) ilə: ölkəyə uyğun UZUNLUQ qaydası (``is_possible_number``). Nömrə
  diapazonu (operator prefiksi) yoxlanmır — yeni operator kodu real istifadəçini bloklamasın.
* ``+`` ilə başlayan nömrə beynəlxalq sayılır və seçilmiş ölkəni üstələyir; əks halda nömrə seçilmiş ölkənin
  yerli formasında oxunur (Azərbaycan: ``050 123 45 67``, ``0501234567``, ``501234567`` hamısı eynidir).
* Ölkə adları CLDR-dən (``core/data/phone_country_names.json``: az / en / ru / tr / de) — əlavə asılılıq yoxdur.
* Telefon DƏYƏRİ heç vaxt loga yazılmır; xəta mesajları dəyər saxlamır.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils import translation
from django.utils.translation import pgettext

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType, ValidationResult

_CTX = "core.phone"

#: Defolt ölkə — Azərbaycan (+994). Seçici həmişə bununla açılır, istifadəçi dəyişə bilər.
DEFAULT_REGION = "AZ"

#: Dəstəklənən dillər (``LANGUAGES``) — ad cədvəlində olmayan dil ingiliscəyə düşür.
_NAME_LANGS = ("az", "en", "ru", "tr", "de")
_FALLBACK_LANG = "en"

#: Nümunə (placeholder) üçün əl ilə düzəliş — libphonenumber AZ üçün ``040 …`` nümunəsini verir.
_EXAMPLE_OVERRIDES = {"AZ": "050 123 45 67"}

_ALLOWED = re.compile(r"^\+?[0-9()\-\s.]+$")
_DATA_FILE = Path(__file__).resolve().parent / "data" / "phone_country_names.json"


@dataclass(frozen=True)
class CountryOption:
    iso: str
    name: str
    dial: str
    flag: str
    example: str
    main: bool
    search: str


@dataclass(frozen=True)
class PhoneParts:
    """Saxlanmış nömrənin forma üçün ayrılmış halı."""

    region: str
    national: str
    parsed: bool


# ── Ölkə siyahısı ───────────────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _names() -> dict:
    with _DATA_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def supported_regions() -> frozenset:
    return frozenset(phonenumbers.SUPPORTED_REGIONS)


def normalize_region(raw) -> str:
    """POST-dan gələn ölkə kodu → dəstəklənən ISO-2; tanınmırsa defolt (Azərbaycan)."""
    value = str(raw or "").strip().upper()
    return value if value in supported_regions() else DEFAULT_REGION


def flag_emoji(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(char) - ord("A")) for char in iso if "A" <= char <= "Z")


def _language(language) -> str:
    code = str(language or translation.get_language() or _FALLBACK_LANG).split("-")[0].lower()
    return code if code in _NAME_LANGS else _FALLBACK_LANG


def _sort_key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold().replace("ə", "e").replace("ı", "i"))
    return "".join(char for char in folded if not unicodedata.combining(char))


def example_national(region: str) -> str:
    """Ölkənin mobil nömrəsinin yerli formada nümunəsi (xananın placeholder-i)."""
    region = normalize_region(region)
    if region in _EXAMPLE_OVERRIDES:
        return _EXAMPLE_OVERRIDES[region]
    sample = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE) or phonenumbers.example_number(region)
    return phonenumbers.format_number(sample, PhoneNumberFormat.NATIONAL) if sample else ""


@lru_cache(maxsize=len(_NAME_LANGS))
def _options_for(language: str) -> tuple:
    names = _names()
    options = []
    for iso in phonenumbers.SUPPORTED_REGIONS:
        entry = names.get(iso) or {}
        name = entry.get(language) or entry.get(_FALLBACK_LANG) or iso
        dial = str(phonenumbers.country_code_for_region(iso))
        english = entry.get(_FALLBACK_LANG) or iso
        # Axtarış üçün əlavə mətn: diakritiksiz ad («turkiye»), ingiliscə ad («turkey») və ISO kod.
        search = " ".join(dict.fromkeys((_sort_key(name), _sort_key(english), iso.lower())))
        options.append(
            CountryOption(
                iso=iso,
                name=name,
                dial=dial,
                flag=flag_emoji(iso),
                example=example_national(iso),
                main=phonenumbers.region_code_for_country_code(int(dial)) == iso,
                search=search,
            )
        )
    options.sort(key=lambda option: (option.iso != DEFAULT_REGION, _sort_key(option.name)))
    return tuple(options)


def country_options(language=None) -> tuple:
    """Seçici üçün bütün ölkələr: Azərbaycan birinci, qalanı ada görə əlifba sırası ilə."""
    return _options_for(_language(language))


def dial_code(region: str) -> str:
    return str(phonenumbers.country_code_for_region(normalize_region(region)))


# ── Saxlanmış nömrə → forma ─────────────────────────────────────────────────────────────────────────────


def split_phone(value) -> PhoneParts:
    """Saxlanmış nömrəni (``+994501234567`` və ya köhnə sərbəst mətn) (ölkə, yerli nömrə) cütünə ayırır.

    Ölkə nömrənin özündən tanınır (``+90…`` → Türkiyə). ``+``-sız köhnə dəyər Azərbaycan nömrəsi sayılır.
    Oxunmayan dəyər olduğu kimi qalır (``parsed=False``) ki, istifadəçi onu görüb düzəltsin.
    """
    text = str(value or "").strip()
    if not text:
        return PhoneParts(DEFAULT_REGION, "", True)
    try:
        number = phonenumbers.parse(text, None if text.startswith("+") else DEFAULT_REGION)
    except NumberParseException:
        return PhoneParts(DEFAULT_REGION, text, False)
    region = phonenumbers.region_code_for_number(number) or phonenumbers.region_code_for_country_code(
        number.country_code
    )
    if not region or region not in supported_regions():
        return PhoneParts(DEFAULT_REGION, text, False)
    return PhoneParts(region, phonenumbers.format_number(number, PhoneNumberFormat.NATIONAL), True)


def display_phone(value) -> str:
    """Göstərmə üçün beynəlxalq format (``+994 50 123 45 67``); oxunmursa olduğu kimi."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = phonenumbers.parse(text, None if text.startswith("+") else DEFAULT_REGION)
    except NumberParseException:
        return text
    if not phonenumbers.is_possible_number(number):
        return text
    return phonenumbers.format_number(number, PhoneNumberFormat.INTERNATIONAL)


# ── Yoxlama ─────────────────────────────────────────────────────────────────────────────────────────────


def _invalid(example: str) -> ValidationError:
    return ValidationError(
        pgettext(_CTX, "Telefon nömrəsi düzgün deyil (məs. %(example)s).") % {"example": example}, code="invalid"
    )


def clean_phone(raw, region=None, *, required: bool = False) -> str:
    """Nömrəni ``region``-a görə yoxlayıb E.164-ə (``+994501234567``) gətirir; boşdursa ``""`` (və ya xəta).

    ``+`` ilə başlayan nömrə beynəlxalq oxunur və ``region``-u üstələyir. Uzunluq ölkəyə görə yoxlanır —
    Azərbaycan üçün 9 rəqəm (operator + 7), Türkiyə üçün 10 və s.
    """
    text = " ".join(str(raw or "").split())
    if not text:
        if required:
            raise ValidationError(pgettext(_CTX, "Telefon nömrəsini yazın."), code="required")
        return ""
    region = normalize_region(region)
    example = example_national(region)
    if not _ALLOWED.match(text):
        raise _invalid(example)
    try:
        number = phonenumbers.parse(text, None if text.startswith("+") else region)
    except NumberParseException as exc:
        raise _invalid(example) from exc
    verdict = phonenumbers.is_possible_number_with_reason(number)
    if verdict == ValidationResult.TOO_SHORT:
        raise ValidationError(
            pgettext(_CTX, "Nömrə çox qısadır (məs. %(example)s).") % {"example": example}, code="too_short"
        )
    if verdict == ValidationResult.TOO_LONG:
        raise ValidationError(
            pgettext(_CTX, "Nömrə çox uzundur (məs. %(example)s).") % {"example": example}, code="too_long"
        )
    if verdict != ValidationResult.IS_POSSIBLE:
        raise _invalid(example)
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def country_field_name(name: str) -> str:
    return f"{name}_country"


def clean_phone_field(data, name: str = "phone", *, required: bool = False) -> str:
    """POST / JSON verilənindən ``<name>`` (yerli nömrə) + ``<name>_country`` (ISO-2) oxuyub E.164 qaytarır."""
    return clean_phone(data.get(name), data.get(country_field_name(name)), required=required)


def resolve_phone_update(data, name: str, current, *, required: bool = False) -> str:
    """Mövcud profilin telefonunu yeniləyərkən yeni saxlanacaq dəyər.

    Forma dəyişməyibsə (istifadəçi köhnə, oxunmayan dəyərə toxunmayıb) mövcud dəyər olduğu kimi qalır —
    əks halda köhnə sərbəst mətn («555000») BÜTÜN profil saxlanmasını bloklayardı. Dəyişibsə ölkəyə görə
    yoxlanır və E.164 qaytarılır.
    """
    posted = " ".join(str(data.get(name) or "").split())
    region = normalize_region(data.get(country_field_name(name)))
    existing = str(current or "").strip()
    if existing:
        parts = split_phone(existing)
        if posted == " ".join(parts.national.split()) and region == parts.region:
            try:
                return clean_phone(posted, region, required=required) if parts.parsed else existing
            except ValidationError:
                return existing
    return clean_phone(posted, region, required=required)


__all__ = [
    "DEFAULT_REGION",
    "CountryOption",
    "PhoneParts",
    "clean_phone",
    "clean_phone_field",
    "country_field_name",
    "country_options",
    "dial_code",
    "display_phone",
    "example_national",
    "flag_emoji",
    "normalize_region",
    "resolve_phone_update",
    "split_phone",
    "supported_regions",
]
