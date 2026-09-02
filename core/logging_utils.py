"""Log sətrinə düşən istifadəçi dəyərləri üçün təhlükəsizləşdirici.

``SensitiveDataFilter`` (``core/logging_filters.py``) SİRLƏRİ maskalayır; bu
modul isə ondan fərqli bir riski bağlayır — **log injection**: istifadəçidən
gələn dəyərdə ``\\n`` / ``\\r`` olarsa saxta log sətri «uydurula» bilər
(operator və ya log-aqreqator onu ayrıca hadisə kimi oxuyar), ANSI/idarəedici
simvollar isə terminal çıxışını korlaya bilər.

Qayda: log mesajına gedən hər istifadəçi mənşəli dəyər əvvəlcə
:func:`safe_log_value`-dən keçir (ideal halda ümumiyyətlə ID loglanır).
"""

from __future__ import annotations

import re

#: Yeni sətir, tab, ANSI-escape və digər idarəedici simvollar.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

#: Log sətrinin şişməməsi üçün standart hədd.
DEFAULT_LOG_VALUE_LIMIT = 120


def safe_log_value(value: object, *, limit: int = DEFAULT_LOG_VALUE_LIMIT) -> str:
    """İstifadəçi dəyərini log üçün təhlükəsiz, tək sətirlik mətnə çevirir."""
    text = _CONTROL_CHARS.sub(" ", str(value))
    # `replace` ayrıca saxlanılır: idarəedici simvol sinfi dəyişsə belə sətir
    # sonlandırıcıları hər halda getməlidir.
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


__all__ = ["DEFAULT_LOG_VALUE_LIMIT", "safe_log_value"]
