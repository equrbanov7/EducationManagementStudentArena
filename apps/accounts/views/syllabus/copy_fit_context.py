"""Təkrar istifadə dialoqunun «dərs saatları fərqlidir» ön baxışı (sahib 2026-11-26) — accounts glue.

Qərar ``apps.syllabus.services.copy_fit``-dədir (yazı yolu ilə EYNİ funksiya); burada yalnız mənbə kartının
mətnləri qurulur:

* ``line``    — «Mənbə: 45 saat (15 həftə) · Bu jurnal: 25 saat (13 sətir)»;
* ``warning`` — «Dərs saatları fərqlidir» / «Mənbənin dərs saatı məlum deyil»;
* ``action``  — kopyalanarkən nə olacaq: «… sondan N sətir kəsiləcək» / «… N boş sətir əlavə olunacaq»;
* ``confirm`` — «Kopyala və uyğunlaşdır» İKİNCİ kliklə icra olunur (birinci klik xəbərdarlığı göstərir).

SORĞU BÜDCƏSİ: mənbələrin həftəlik cədvəlinin sətir sayı BİR sorğu ilə (``copy_fit.week_row_counts``); mənbənin
saatı sorğusuzdur (``sharing.source_hours`` + çağıranın toplu ``fallback`` xəritəsi).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.public import services

_CTX = "accounts.syllabus"

_LINE = pgettext_lazy(_CTX, "Mənbə: %(source)s · Bu jurnal: %(target)s")
_SOURCE = pgettext_lazy(_CTX, "%(hours)s saat (%(rows)s həftə)")
_SOURCE_UNKNOWN = pgettext_lazy(_CTX, "saat məlum deyil (%(rows)s həftə)")
_TARGET = pgettext_lazy(_CTX, "%(hours)s saat (%(rows)s sətir)")
_TARGET_UNKNOWN = pgettext_lazy(_CTX, "saat məlum deyil")
_WARN_DIFFER = pgettext_lazy(_CTX, "Dərs saatları fərqlidir")
_WARN_UNKNOWN = pgettext_lazy(_CTX, "Mənbənin dərs saatı məlum deyil")
_CUT = pgettext_lazy(
    _CTX,
    "Kopyalananda qaralama bu jurnalın saatını alır, həftəlik plan %(rows)s sətrə gətirilir: sondan %(count)s sətir "
    "kəsiləcək.",
)
_ADD = pgettext_lazy(
    _CTX,
    "Kopyalananda qaralama bu jurnalın saatını alır, həftəlik plan %(rows)s sətrə gətirilir: %(count)s boş sətir "
    "əlavə olunacaq.",
)
_KEEP = pgettext_lazy(
    _CTX,
    "Kopyalananda qaralama bu jurnalın saatını alır; sətir sayı eynidir (%(rows)s) — saatlar bu jurnalın planına görə "
    "yenidən bölünəcək.",
)
_TARGET_UNKNOWN_NOTE = pgettext_lazy(
    _CTX, "Bu jurnalın rəsmi dərs saatı tapılmadı — həftəlik plan olduğu kimi köçürülür, saatı redaktorda seçin."
)
_CONFIRM_LABEL = pgettext_lazy(_CTX, "Bəli, uyğunlaşdırıb kopyala")
_CONFIRM_HINT = pgettext_lazy(_CTX, "Davam etmək üçün düyməni bir daha basın.")


def _base(row):
    return row.approved_version if row.approved_version_id else row.current_version


def _action(plan) -> str:
    if plan["state"] == services.copy_fit.TARGET_UNKNOWN:
        return str(_TARGET_UNKNOWN_NOTE)
    if not plan["fit"]:
        return ""
    params = {"rows": plan["target_rows"]}
    if plan["cut"]:
        return str(_CUT) % {**params, "count": plan["cut"]}
    if plan["added"]:
        return str(_ADD) % {**params, "count": plan["added"]}
    return str(_KEEP) % params


def payload(plan) -> dict:
    """Bir mənbə kartının ``copy_fit`` sahəsi (``copy_fit.copy_plan`` nəticəsindən)."""
    state = plan["state"]
    copy_fit = services.copy_fit
    if state == copy_fit.SOURCE_UNKNOWN:
        source = str(_SOURCE_UNKNOWN) % {"rows": plan["source_rows"]}
    else:
        source = str(_SOURCE) % {"hours": plan["source_hours"], "rows": plan["source_rows"]}
    if state == copy_fit.TARGET_UNKNOWN:
        target = str(_TARGET_UNKNOWN)
    else:
        target = str(_TARGET) % {"hours": plan["target_hours"], "rows": plan["target_rows"]}
    warning = {copy_fit.DIFFER: _WARN_DIFFER, copy_fit.SOURCE_UNKNOWN: _WARN_UNKNOWN}.get(state)
    return {
        **plan,
        "line": str(_LINE) % {"source": source, "target": target},
        "warning": str(warning) if warning else "",
        "action": _action(plan),
        "confirm": plan["fit"],
        "confirm_label": str(_CONFIRM_LABEL),
        "confirm_hint": str(_CONFIRM_HINT),
    }


def fit_map(rows, target, fallback=None) -> dict:
    """``{syllabus_id: copy_fit}`` — dialoqun bütün mənbə kartları üçün (sətir sayı TƏK sorğu)."""
    rows = list(rows)
    if not rows:
        return {}
    fallback = fallback or {}
    counts = services.copy_fit.week_row_counts([_base(row) for row in rows])
    result = {}
    for row in rows:
        base = _base(row)
        plan = services.copy_fit.copy_plan(
            source_hours_value=services.sharing.source_hours(row, fallback.get(row.pk)),
            target_hours=target.plan_hours,
            row_count=counts.get(getattr(base, "pk", None), 0),
        )
        result[row.pk] = payload(plan)
    return result


__all__ = ["fit_map", "payload"]
