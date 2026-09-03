"""`ems_ui` şablon kitabxanası — paylaşılan komponent qatının Django tərəfi.

NİYƏ `apps.accounts`-dadır? `core` INSTALLED_APPS-da deyil, ona görə
`core/templatetags/` avtomatik tapılmır. Məntiq (status kataloqu) saf şəkildə
`core/ui/status_catalog.py`-dədir; bu fayl yalnız onun şablon adapteridir.
`apps → core` istiqaməti module_deps ratchet-i üçün təhlükəsizdir.

İstifadə::

    {% load ems_ui %}
    {% ems_status_badge "syllabus" row.status %}
    {% ems_status_badge "workload_line" line.state wrap=True %}
    {% ems_next_step "syllabus" row.status %}
    {{ row.status|ems_status_label:"syllabus" }}
"""

from __future__ import annotations

from django import template
from django.utils.translation import pgettext_lazy

from core.ui import status_catalog

register = template.Library()

#: Naməlum açar üçün neytral fallback — şablon HEÇ VAXT boş badge verməsin.
_UNKNOWN = status_catalog.Status(
    key="",
    label=pgettext_lazy("ui.status", "Naməlum"),
    tone="neutral",
)


def _resolve(family: str, key) -> status_catalog.Status:
    """`family`/`key` cütünü statusa çevirir; tapılmasa naməlum fallback."""
    if key is None:
        return _UNKNOWN
    try:
        found = status_catalog.get(family, str(key))
    except status_catalog.UnknownStatusFamily:
        # Ailə adı səhvdirsə bunu GİZLƏTMİRİK — dev-də dərhal görünsün.
        raise
    if found is not None:
        return found
    # Açar kataloqda yoxdur: etiket kimi açarın özünü göstəririk (boş badge yox).
    return status_catalog.Status(key=str(key), label=str(key), tone="neutral")


@register.simple_tag(name="ems_status")
def ems_status(family: str, key):
    """Status obyektini qaytarır — şablonda `.label` / `.tone` / `.css_class`."""
    return _resolve(family, key)


@register.inclusion_tag("partials/ems_ui/_status_badge.html", name="ems_status_badge")
def ems_status_badge(family: str, key, wrap: bool = False, dot: bool = False):
    """Status badge-i render edir.

    KONTEKST MÜQAVİLƏSİ (`_status_badge.html`):
      `status` — `core.ui.status_catalog.Status`
      `wrap`   — uzun etiket sarılsın (`.ems-badge--wrap`)
      `dot`    — etiketdən əvvəl rəngli nöqtə göstərilsin
    """
    return {"status": _resolve(family, key), "wrap": bool(wrap), "dot": bool(dot)}


@register.simple_tag(name="ems_next_step")
def ems_next_step(family: str, key):
    """Statusun «növbəti addım» mətni (yoxdursa boş sətir)."""
    status = _resolve(family, key)
    return status.next_step or ""


@register.simple_tag(name="ems_status_family")
def ems_status_family(family: str):
    """Bütün ailəni qaytarır — qalereya və filtr seçiciləri üçün."""
    return status_catalog.family(family)


@register.filter(name="ems_status_label")
def ems_status_label(key, family: str):
    """`{{ row.status|ems_status_label:"syllabus" }}`."""
    return _resolve(family, key).label


@register.filter(name="ems_status_tone")
def ems_status_tone(key, family: str):
    """`{{ row.status|ems_status_tone:"syllabus" }}` → ton adı."""
    return _resolve(family, key).tone


@register.filter(name="ems_status_class")
def ems_status_class(key, family: str):
    """Hazır CSS class sətri — badge-dən kənar yerlərdə (nöqtə, kart konturu)."""
    return _resolve(family, key).css_class


@register.simple_tag(name="ems_pct_style")
def ems_pct_style(value) -> str:
    """Progress zolağı üçün DİNAMİK faiz.

    CLAUDE.md statik inline stili qadağan edir; dinamik dəyər isə CSS custom
    property ilə ötürülür (`--ems-bar-pct`), CSS onu `width`-ə bağlayır.
    Dəyər 0–100 aralığına sıxılır ki, korlanmış data layout-u pozmasın.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    number = max(0.0, min(100.0, number))
    return f"--ems-bar-pct:{number:.4g}%"
