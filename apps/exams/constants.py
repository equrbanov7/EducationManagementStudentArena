import re

# Constants for exam parsing

# Sualların variantları üçün mümkün etiketlər
LABELS = ["A", "B", "C", "D", "E"]

# Sualların, variantların və cavab sətrlərinin tanınması üçün regex-lər
QUESTION_RE = re.compile(r"^\s*(\d+)\s*[\)\.]\s*(.+)\s*$")

# Variant sətrləri: opsional "*", sonra A-E, sonra ")" və ya ".", sonra variant mətni
OPTION_RE = re.compile(r"^\s*(\*)?\s*([A-E])\s*[\)\.]\s*(.+)\s*$", re.IGNORECASE)

# Cavab sətrləri: "cavab", "duz cavab", "düz cavab" və ya "correct" ilə başlayır, sonra ":" və ya "-", sonra A-E variantları (bir neçə ola bilər)
ANSWERLINE_RE = re.compile(
    r"^\s*(cavab|duz\s*cavab|düz\s*cavab|correct)\s*[:\-]\s*([A-E](?:\s*[,;/]\s*[A-E])*)\s*$",
    re.IGNORECASE,
)
