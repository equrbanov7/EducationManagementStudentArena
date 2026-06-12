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
