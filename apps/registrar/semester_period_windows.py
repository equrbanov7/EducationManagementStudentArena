"""«Semestr açılışı» dövr dialoqunun TƏQVİM PƏNCƏRƏLƏRİ — oxuma + doğrulama.

2026-10-19: ``AcademicPeriod.exam_session_start/end`` və
``registration_start/end`` yalnız Django admin-dən dəyişirdi, halbuki onlar
bunları idarə edir:

* imtahan balı dövr kilidi (``exam_score_period_lock`` — bağlanma = max(bitmə, sessiya sonu));
* Mühasibatlığın tədris pəncərəsi (``accounts.services.accounting.periods``);
* seçmə fənn qeydiyyatı (``registrar.services.choose_group_elective``);
* «Akademik təqvim» bölməsinin «Pəncərəsi yoxdur» göstəricisi.

QAYDALAR
--------
* Hər pəncərə CÜT-dür: ya hər iki tarix, ya heç biri (yarımçıq pəncərə
  oxucular üçün «konfiqurasiya edilməyib» deməkdir — səssiz itki olmasın).
* Bitmə ≥ başlama (eyni gün olar) — əks halda **xəta**.
* Dövrə münasibət **xəbərdarlıqdır** (yazını bloklamır):
  - qeydiyyat pəncərəsi dövrün içində və ya ona BİTİŞİK olmalıdır
    (:data:`ADJACENT_DAYS` gün əvvəl/sonra — seçim adətən semestrdən qabaq olur);
  - imtahan sessiyası semestr daxilində (və ya bitişik) BAŞLAMALIDIR; sonu
    ``end_date``-dən SONRAYA uzana bilər (yekun sessiya semestrdən sonra bitir).
* POST-da OLMAYAN sahə dövrün MÖVCUD dəyərini saxlayır (qismən yeniləmə);
  göndərilmiş BOŞ sahə pəncərəni silir.
"""

from __future__ import annotations

import datetime
import json

from django.utils.translation import pgettext

_CTX = "accounts.semester"

#: Pəncərənin dövrə «bitişik» sayıldığı məsafə (gün).
ADJACENT_DAYS = 31

EXAM_FIELDS = ("exam_session_start", "exam_session_end")
REGISTRATION_FIELDS = ("registration_start", "registration_end")
WINDOW_FIELDS = EXAM_FIELDS + REGISTRATION_FIELDS


class WindowError(Exception):
    """Pəncərə doğrulanmadı — HTTP qatı 400 + ``field`` qaytarır (pozisional konstruktor, B042)."""

    def __init__(self, code: str, message: str, field: str):
        super().__init__(code, message, field)
        self.code = code
        self.message = message
        self.field = field


def _as_date(value):
    if value is None or isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def read_windows(post, instance) -> dict:
    """POST + mövcud dövrdən dörd tarix (``date`` və ya ``None``)."""
    values = {}
    for name in WINDOW_FIELDS:
        if name not in post:
            values[name] = _as_date(getattr(instance, name, None)) if instance is not None else None
            continue
        raw = (post.get(name) or "").strip()
        if not raw:
            values[name] = None
            continue
        try:
            values[name] = datetime.date.fromisoformat(raw)
        except ValueError:
            raise WindowError("bad_date", pgettext(_CTX, "Tarix düzgün deyil."), name) from None
    return values


def _check_pair(values, start_field, end_field, label):
    start, end = values[start_field], values[end_field]
    if (start is None) != (end is None):
        raise WindowError(
            "window_incomplete",
            pgettext(_CTX, "%(window)s üçün həm başlanğıc, həm də son tarix göstərilməlidir.") % {"window": label},
            end_field if end is None else start_field,
        )
    if start is not None and end < start:
        raise WindowError(
            "window_order",
            pgettext(_CTX, "%(window)s: son tarix başlanğıcdan əvvəl ola bilməz.") % {"window": label},
            end_field,
        )


def validate_windows(values, *, period_start, period_end) -> list:
    """Xətada :class:`WindowError`; uğurda XƏBƏRDARLIQ mətnlərinin siyahısı."""
    exam_label = pgettext(_CTX, "İmtahan sessiyası")
    registration_label = pgettext(_CTX, "Seçim (qeydiyyat) pəncərəsi")
    _check_pair(values, *EXAM_FIELDS, exam_label)
    _check_pair(values, *REGISTRATION_FIELDS, registration_label)

    period_start, period_end = _as_date(period_start), _as_date(period_end)
    near = datetime.timedelta(days=ADJACENT_DAYS)
    warnings = []
    exam_start = values["exam_session_start"]
    if exam_start is not None and not (period_start <= exam_start <= period_end + near):
        warnings.append(pgettext(_CTX, "İmtahan sessiyası semestr tarixləri daxilində başlamır — tarixləri yoxlayın."))
    reg_start, reg_end = values["registration_start"], values["registration_end"]
    if reg_start is not None and (reg_start < period_start - near or reg_end > period_end + near):
        warnings.append(pgettext(_CTX, "Seçim pəncərəsi semestr tarixlərindən xeyli kənardadır — tarixləri yoxlayın."))
    return warnings


def windows_snapshot(source) -> dict:
    """Audit üçün dörd tarix ISO mətni kimi (``source`` — dövr və ya :func:`read_windows` nəticəsi)."""
    out = {}
    for name in WINDOW_FIELDS:
        value = source.get(name) if isinstance(source, dict) else getattr(source, name, None)
        value = _as_date(value)
        out[name] = value.isoformat() if value else ""
    return out


def period_edit_prefill(period) -> str:
    """«Dövrü redaktə et» dialoqunun ``data-tof-prefill`` JSON-u (təqvim pəncərələri daxil)."""
    dates = {name: getattr(period, name, None) for name in ("start_date", "end_date") + WINDOW_FIELDS}
    payload = {
        "action": "save_period",
        "id": str(period.id),
        "name": period.name,
        "academic_year": period.academic_year,
        **{name: (_as_date(value).isoformat() if value else "") for name, value in dates.items()},
    }
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "ADJACENT_DAYS",
    "WINDOW_FIELDS",
    "WindowError",
    "period_edit_prefill",
    "read_windows",
    "validate_windows",
    "windows_snapshot",
]
