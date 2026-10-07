"""OOXML (xlsx/docx/pptx) paketlərinin açılma (decompression) büdcəsi.

Təhlükəsizlik auditi 2026-10-07: ``core/upload_security.py`` modul limitinə
çatdığı üçün ayrıca modul (``core/upload_markup.py`` nümunəsi).
"""

from __future__ import annotations

import io
import zipfile

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

#: OOXML (xlsx/docx/pptx) paketinin bir hissə sayı tavanı — real fayllar onlarla olur.
OOXML_MAX_MEMBERS = 512


def validate_ooxml_expansion(source, *, max_expanded_bytes: int, max_members: int = OOXML_MAX_MEMBERS) -> None:
    """OOXML paketinin AÇILMIŞ ölçüsünü parser-dən (``openpyxl``) ƏVVƏL məhdudlaşdır.

    Təhlükəsizlik auditi 2026-10-07: ``load_workbook(read_only=True)`` vərəqləri
    axınla oxuyur, amma ``sharedStrings.xml``-i TAM yaddaşa yığır — 5 MB-lıq
    `.xlsx` təkrarlanan sətirlərlə GB-larla açıla bilər (veb worker OOM).
    Python ``zipfile`` heç vaxt elan olunan ``file_size``-dan çox bayt qaytarmır,
    ona görə mərkəzi kataloqdakı ölçülərin cəmi etibarlı yuxarı həddir.

    ``source`` — ``bytes`` və ya fayl obyekti (mövqe geri qaytarılır).
    Rədd olunanda ``ValidationError`` (``code``: ``invalid_archive`` /
    ``too_many_members`` / ``expanded_too_large``).
    """

    if isinstance(source, (bytes, bytearray)):
        stream, restore = io.BytesIO(source), None
    else:
        stream = source
        try:
            restore = stream.tell()
            stream.seek(0)
        except Exception:
            restore = None
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
    except Exception:
        raise ValidationError(
            pgettext("upload.security.error", "Yüklənmiş fayl etibarsız ZIP arxividir."), code="invalid_archive"
        )
    finally:
        if restore is not None:
            try:
                stream.seek(restore)
            except Exception:
                pass
    if len(entries) > max_members:
        raise ValidationError(
            pgettext(
                "upload.security.error",
                "ZIP arxivi çox sayda fayl ehtiva edir (maksimum {max} icazə verilir).",
            ).format(max=max_members),
            code="too_many_members",
        )
    if sum(max(0, entry.file_size) for entry in entries) > max_expanded_bytes:
        raise ValidationError(
            pgettext("upload.security.error", "Fayl ölçüsü limiti keçildi (maksimum {max_size_mb} MB).").format(
                max_size_mb=max(1, int(max_expanded_bytes // (1024 * 1024)))
            ),
            code="expanded_too_large",
        )


__all__ = ["OOXML_MAX_MEMBERS", "validate_ooxml_expansion"]
