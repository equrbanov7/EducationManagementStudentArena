"""extraction paketi — constants."""

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


MAX_UPLOAD_BYTES = getattr(settings, "EXAM_UPLOAD_MAX_BYTES", 45 * 1024 * 1024)


FILE_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
}


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


# İstifadəçi marker-i əl ilə yazır və tez-tez alt-xətti təkrarlayır
# ("END__QUESTION"). Bir və ya bir neçə alt-xətt qəbul olunur ki, belə yazılış
# blok sərhədi kimi tanınsın və mətnə sızmasın.
END_QUESTION_RE = re.compile(r"^\s*END_+QUESTION\s*$", re.IGNORECASE)


JOINED_OPTION_BOUNDARY_RE = re.compile(r"(?<=[a-zəöüğışçа-яё])(?=[A-ZƏÖÜĞİŞÇА-ЯЁ])")


_BULLET_CHARS = "•◦▪‣●○·"


_CHECK_CHARS = "√✓✔☑✅"


_BULLET_OPTION_LINE_RE = re.compile(rf"^\s*[{_BULLET_CHARS}]\s*(.+)$")


_CHECK_OPTION_LINE_RE = re.compile(rf"^\s*[{_CHECK_CHARS}]\s*(.+)$")


_CYRILLIC_SEQ_MAP = {"А": "A", "Б": "B", "В": "C", "Г": "D", "Д": "E"}


_CYRILLIC_LOOKALIKE_MAP = {"А": "A", "В": "B", "С": "C", "Д": "D", "Е": "E"}


_CYR_OPTION_LABEL_RE = re.compile(r"^(\s*\*?\s*)([АБВГДСЕабвгдсе])(\s*[\)\.])", re.MULTILINE)


_CYR_ANSWERLINE_RE = re.compile(
    r"^(\s*(?:cavab|duz\s*cavab|düz\s*cavab|correct|answer|ответ|правильный\s*ответ|cevap|doğru\s*cevap)\s*[:\-]\s*)"
    r"([АБВГДСЕабвгдсе](?:\s*[,;/]\s*[АБВГДСЕабвгдсе])*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


_BARE_QNO_RE = re.compile(r"^\s*(\d{1,4})\s*([\.\)])\s*$")


_HIGHLIGHT_CORE_RE = re.compile(r"[^0-9a-zəğıöüçşıа-яё]+")
