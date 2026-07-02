import re

# Constants for exam parsing

# Sualların variantları üçün mümkün etiketlər
LABELS = ["A", "B", "C", "D", "E"]

# ---------------------------------------------------------------------------
# İmtahan / sual dilləri (çoxdilli imtahan dəstəyi)
#
# Layihənin `settings.LANGUAGES` siyahısı ilə eyni kodları istifadə edirik,
# amma sabitlər burada saxlanılır ki, migration-lar settings-dən asılı olmasın
# və dil seçimləri sabit qalsın. Display adları lokalizasiya OLUNMUR — dilin öz
# ana adı göstərilir.
# ---------------------------------------------------------------------------
LANGUAGE_AZ = "az"
LANGUAGE_EN = "en"
LANGUAGE_RU = "ru"
LANGUAGE_TR = "tr"

EXAM_LANGUAGE_CHOICES = (
    (LANGUAGE_AZ, "Azərbaycan dili"),
    (LANGUAGE_EN, "English"),
    (LANGUAGE_RU, "Русский"),
    (LANGUAGE_TR, "Türkçe"),
)

# Köhnə (tək-dilli) imtahanlar üçün default dil. Data migration mövcud bütün
# imtahan/sualları bu dilə bağlayır ki, geriyə uyğunluq pozulmasın.
DEFAULT_EXAM_LANGUAGE = LANGUAGE_AZ

EXAM_LANGUAGE_VALUES = frozenset(code for code, _label in EXAM_LANGUAGE_CHOICES)

# Sualların, variantların və cavab sətrlərinin tanınması üçün regex-lər
QUESTION_RE = re.compile(r"^\s*(\d+)\s*(?:\)\s*|\.(?!\d)\s*)(.+)\s*$")

# Variant sətrləri: opsional "*", sonra A-E, sonra ")" və ya ".", sonra variant mətni
OPTION_RE = re.compile(r"^\s*(\*)?\s*([A-E])\s*[\)\.]\s*(.+)\s*$", re.IGNORECASE)

# Cavab sətrləri: "cavab"/"correct"/"answer"/"ответ"/"cevap" ilə başlayır,
# sonra ":" və ya "-", sonra A-E variantları (bir neçə ola bilər). 4 dil: az/en/ru/tr.
ANSWERLINE_RE = re.compile(
    r"^\s*(cavab|duz\s*cavab|düz\s*cavab|correct|answer|"
    r"ответ|правильный\s*ответ|cevap|doğru\s*cevap)"
    r"\s*[:\-]\s*([A-E](?:\s*[,;/]\s*[A-E])*)\s*$",
    re.IGNORECASE,
)

# ===========================================================================
# Müəllim paneli — imtahan "həyat dövrü" (lifecycle) statusları
# ---------------------------------------------------------------------------
# Hesablanmış status (DB-də saxlanmır, `Exam.lifecycle_status` ilə törədilir).
# Bu keylər həm modeldə, həm KPI sayğaclarında, həm də şablon filtrlərində
# istifadə olunur — status məntiqi tək mənbədən idarə olunsun.
# ===========================================================================
EXAM_STATUS_ACTIVE = "active"
EXAM_STATUS_SCHEDULED = "scheduled"
EXAM_STATUS_DRAFT = "draft"
EXAM_STATUS_ARCHIVED = "archived"

# Müəllim panelində bölmələrin göstərilmə sırası.
EXAM_STATUS_ORDER = (
    EXAM_STATUS_ACTIVE,
    EXAM_STATUS_SCHEDULED,
    EXAM_STATUS_DRAFT,
    EXAM_STATUS_ARCHIVED,
)

# Status üçün vizual tokenlər (rəng, yumşaq fon, dərin mətn, FontAwesome ikon).
# Mətnlər (label/hint) şablonda tərcümə olunur — burada yalnız brend rəngləri.
EXAM_STATUS_META = {
    EXAM_STATUS_ACTIVE: {"color": "#16A34A", "soft": "#DCFCE7", "deep": "#15803D", "icon": "fa-bolt"},
    EXAM_STATUS_SCHEDULED: {"color": "#2C5BFF", "soft": "#EEF2FF", "deep": "#1E40AF", "icon": "fa-clock"},
    EXAM_STATUS_DRAFT: {"color": "#64748B", "soft": "#F1F4F9", "deep": "#475569", "icon": "fa-pen-ruler"},
    EXAM_STATUS_ARCHIVED: {"color": "#B45309", "soft": "#FEF3C7", "deep": "#92400E", "icon": "fa-box-archive"},
}

# İmtahan növü (Exam.exam_type) üçün vizual tokenlər + ikon.
EXAM_TYPE_META = {
    "test": {"color": "#0284C7", "soft": "#E0F2FE", "deep": "#075985", "icon": "fa-list-ul"},
    "written": {"color": "#BE3455", "soft": "#FCE7EE", "deep": "#9F1239", "icon": "fa-pen-fancy"},
    "coding": {"color": "#7C3AED", "soft": "#F2ECFE", "deep": "#5B21B6", "icon": "fa-code"},
}

# Kateqoriya (Exam.exam_type_extended) üçün vizual tokenlər.
# Dashboard çipləri yalnız əsas 3-ü göstərir; qalanları kartda öz rəngi ilə çıxır.
EXAM_CATEGORY_META = {
    "final": {"color": "#BE3455", "soft": "#FCE7EE", "deep": "#9F1239"},
    "midterm": {"color": "#2C5BFF", "soft": "#EEF2FF", "deep": "#1E40AF"},
    "quiz": {"color": "#0F766E", "soft": "#E6FBF7", "deep": "#0B544E"},
    "placement": {"color": "#B45309", "soft": "#FEF3C7", "deep": "#92400E"},
    "practice": {"color": "#0891B2", "soft": "#E0F7FB", "deep": "#155E63"},
}

# Dashboard-da çip kimi göstərilən kateqoriyalar (dizaynla eyni: Final/Midterm/Quiz).
EXAM_CATEGORY_FILTER_ORDER = ("final", "midterm", "quiz")

# ── M2 (2026-07-02): exams→live_exam import-time asılılığını kəsən lazy accessor-lar ──
# Modul yüklənəndə live_exam import OLUNMUR; model yalnız çağırış anında tapılır.


def get_live_session_model():
    """live_exam.LiveSession modelini lazy qaytarır (app-registry lookup)."""
    from django.apps import apps as django_apps

    return django_apps.get_model("live_exam", "LiveSession")


def get_live_active_states():
    """Hələ bitməmiş (aktiv) canlı sessiya state-ləri — lobby/question/reveal."""
    model = get_live_session_model()
    return (model.STATE_LOBBY, model.STATE_QUESTION, model.STATE_REVEAL)
