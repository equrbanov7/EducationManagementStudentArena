"""Qabaqcıl proktorinq seçimləri — ``Exam.settings["proctoring"]`` (miqrasiyasız).

Sahib 2026-10-01: «test yaradarkən nəzarət sistemi … tələbənin extension qoşa
bilmə ehtimalını nəzərə al, hər cür cheat-ə qarşı öncəm olsun». Mövcud
``ExamSupervisionConfig`` sütunları (tam ekran, tab, kopyala/yapışdır, sağ klik,
seçim, qısayollar) toxunulmaz qalır; yeni aşkarlama qatları imtahanın mövcud
``settings`` JSON sahəsində saxlanılır ki, miqrasiya lazım olmasın.

Bütün yeni qatlar YALNIZ QEYD EDİR (pozuntu sayğacını artırmır, tələbəni
kilidləmir) — ona görə defolt olaraq açıqdır və mövcud imtahanları pozmur.
``flag_threshold`` — risk xalı bu həddə çatanda cəhd nəzarətçi/müəllim
ekranında «şübhəli» kimi işarələnir (avtomatik kəsilmə YOXDUR).
"""

from __future__ import annotations

OPTION_KEYS = ("anti_ai", "detect_devtools", "detect_multi_monitor", "detect_text_injection")

DEFAULT_FLAG_THRESHOLD = 12
MIN_FLAG_THRESHOLD = 3
MAX_FLAG_THRESHOLD = 100

#: Forma bu gizli sahəni göndərməyibsə (köhnə forma / başqa klient), seçimlərə
#: toxunulmur — işarəsiz checkbox «söndürülüb» kimi oxunmasın.
FORM_MARKER = "proctoring_advanced_present"


def _clamp_threshold(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FLAG_THRESHOLD
    return max(MIN_FLAG_THRESHOLD, min(MAX_FLAG_THRESHOLD, number))


def default_proctoring_options() -> dict:
    options = {key: True for key in OPTION_KEYS}
    options["flag_threshold"] = DEFAULT_FLAG_THRESHOLD
    return options


def normalize_proctoring_options(raw) -> dict:
    """İstənilən (köhnə/zədəli) JSON-dan təhlükəsiz, tam seçim lüğəti."""
    options = default_proctoring_options()
    if not isinstance(raw, dict):
        return options
    for key in OPTION_KEYS:
        if key in raw:
            options[key] = bool(raw[key])
    if "flag_threshold" in raw:
        options["flag_threshold"] = _clamp_threshold(raw["flag_threshold"])
    return options


def proctoring_options(exam) -> dict:
    settings = getattr(exam, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    return normalize_proctoring_options(settings.get("proctoring"))


def proctoring_options_for_exams(exam_ids) -> dict:
    """{exam_id: seçimlər} — monitor snapshot-u üçün TƏK sorğu."""
    ids = [exam_id for exam_id in set(exam_ids) if exam_id]
    if not ids:
        return {}
    from apps.exams.models import Exam

    rows = Exam.objects.filter(id__in=ids).values_list("id", "settings")
    result = {}
    for exam_id, settings in rows:
        raw = settings.get("proctoring") if isinstance(settings, dict) else None
        result[exam_id] = normalize_proctoring_options(raw)
    return result


def save_proctoring_options_from_form(exam, form_data):
    """Formadan seçimləri yazır; marker yoxdursa heç nəyə toxunmur (None)."""
    if (form_data.get(FORM_MARKER) or "") != "1":
        return None
    options = {key: form_data.get(f"proctoring_{key}") == "on" for key in OPTION_KEYS}
    options["flag_threshold"] = _clamp_threshold(form_data.get("proctoring_flag_threshold"))

    settings = dict(exam.settings or {}) if isinstance(exam.settings, dict) else {}
    if settings.get("proctoring") == options:
        return options
    settings["proctoring"] = options
    # ``update()`` — imtahanın digər sahələrinə/siqnallarına toxunmadan yalnız JSON.
    type(exam).objects.filter(pk=exam.pk).update(settings=settings)
    exam.settings = settings
    return options


__all__ = [
    "DEFAULT_FLAG_THRESHOLD",
    "FORM_MARKER",
    "MAX_FLAG_THRESHOLD",
    "MIN_FLAG_THRESHOLD",
    "OPTION_KEYS",
    "default_proctoring_options",
    "normalize_proctoring_options",
    "proctoring_options",
    "proctoring_options_for_exams",
    "save_proctoring_options_from_form",
]
