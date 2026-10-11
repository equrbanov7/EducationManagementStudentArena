"""«Akademik analitika» — görünüş modeli (2026-10-11 sahib: «səhifəni səliqəyə sal»).

Keşlənən aqreqat (:mod:`apps.registrar.analytics_cache`) DƏYİŞMİR — burada yalnız
ondan kabinetin ortaq KPI komponentinin (`partials/ems_ui/_kpi_tile.html`:
label/value/unit/note/tone) kartları qurulur. Ayrıca moduldur ki, keşə düşən
payload-a dil-asılı mətn yazılmasın (keş bütün dillər arasında paylaşılır).

Qayda: yekunlaşmış (keçdi/kəsildi) nəticə yoxdursa keçid faizi «0,00%» DEYİL,
orta GPA «Hesablana bilmir» DEYİL — hər ikisi «—» və qeyd SƏBƏBİ izah edir.
Qayıb faizi 15%-dən yuxarı olanda kart xəbərdarlıq tonundadır (cədvəldəki
`is-high` həddi ilə eyni).
"""

from __future__ import annotations

from django.utils.translation import pgettext

#: Qayıb faizi bu həddən YUXARI olanda xəbərdarlıq (cədvəl `is-high` ilə eyni).
ABSENCE_WARN_PCT = 15
#: Keçid faizi bu həddən AŞAĞI olanda təhlükə tonu (cədvəl `is-low` ilə eyni).
PASS_LOW_PCT = 60
#: Dəyər yoxdur işarəsi — kartda və cədvəldə eyni.
NA = "—"

_CTX = "registrar.analytics"


def _pass_tile(t: dict) -> dict:
    label = pgettext(_CTX, "Keçid faizi")
    if not t["definite"]:
        return {"label": label, "value": NA, "note": pgettext(_CTX, "Hələ yekunlaşmış qiymət yoxdur")}
    note = pgettext(_CTX, "%(passed)s / %(definite)s yekunlaşmış nəticə") % {
        "passed": t["passed"],
        "definite": t["definite"],
    }
    tone = "accent-danger" if t["pass_rate"] < PASS_LOW_PCT else "accent-success"
    return {"label": label, "value": t["pass_rate"], "unit": "%", "note": note, "tone": tone}


def _gpa_tile(t: dict) -> dict:
    label = pgettext(_CTX, "Orta GPA")
    if not t["avg_gpa_available"]:
        note = pgettext(_CTX, "Yekunlaşmış qiymət olmadan hesablanmır")
        return {"label": label, "value": NA, "note": note}
    return {"label": label, "value": t["avg_gpa"], "note": pgettext(_CTX, "Kredit-çəkili, 100 bal şkalası")}


def _absence_tile(t: dict) -> dict:
    if t["barred"]:
        note = pgettext(_CTX, "Kəsilmə həddində: %(count)s qeydiyyat") % {"count": t["barred"]}
    else:
        note = pgettext(_CTX, "Kəsilmə həddində qeydiyyat yoxdur")
    tile = {"label": pgettext(_CTX, "Qayıb faizi"), "value": t["absence_rate"], "unit": "%", "note": note}
    if t["absence_rate"] > ABSENCE_WARN_PCT:
        tile["tone"] = "accent-warning"
    return tile


def kpi_tiles(data: dict) -> list[dict]:
    """Ümumi göstəricilər — `_kpi_row.html` üçün beş kart (data yoxdursa boş)."""
    t = data.get("totals") if data.get("has_data") else None
    if not t:
        return []
    scope_note = pgettext(_CTX, "Proqram: %(programs)s · qrup: %(groups)s") % {
        "programs": len(data.get("programs") or ()),
        "groups": len(data.get("groups") or ()),
    }
    progress_note = pgettext(_CTX, "Yekunlaşıb: %(done)s · davam edir: %(open)s") % {
        "done": t["definite"],
        "open": t["in_progress"],
    }
    return [
        {"label": pgettext(_CTX, "Tələbə"), "value": t["students"], "note": scope_note},
        {"label": pgettext(_CTX, "Fənn qeydiyyatı"), "value": t["enrollments"], "note": progress_note},
        _pass_tile(t),
        _gpa_tile(t),
        _absence_tile(t),
    ]


def view_context(periods, data: dict, *, embedded: bool) -> dict:
    """Şablon konteksti — `page_contexts.analytics_context` qaytarır."""
    return {
        "periods": periods,
        "analytics": data,
        "analytics_embedded": embedded,
        "analytics_kpis": kpi_tiles(data),
        "analytics_absence_warn": ABSENCE_WARN_PCT,
        "analytics_pass_low": PASS_LOW_PCT,
    }


__all__ = ["ABSENCE_WARN_PCT", "NA", "PASS_LOW_PCT", "kpi_tiles", "view_context"]
