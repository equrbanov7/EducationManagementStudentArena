"""Köhnə qiymət sübutuna aid əlavə, dar mənbə kontraktları.

Əsas ``field_contracts`` modulu 600-sətir ratchet sərhədindədir. İmtahanın
giriş/çıxış cəhdləri ayrıca, credential-safe allowlist ilə burada saxlanır;
beləliklə yeni mənbə səthi mövcud kontraktların barmaq izini dəyişmir.
"""

from .field_contracts import LegacySourceFieldContract

EXAM_ENTRY_EXIT_FIELDS = LegacySourceFieldContract(
    source_table="imthngrscxsblr",
    version="legacy-grade-v1",
    allowed_fields=(
        "id",
        "student_id",
        "lesson_id",
        "giris_point",
        "cixis_point",
        "type",
        "added_date",
    ),
)

SCORE_SHEET_EXPORT_FIELDS = LegacySourceFieldContract(
    source_table="balvereqi_logs",
    version="legacy-grade-v1",
    allowed_fields=(
        "id",
        "owner_id",
        "uniqid",
        "data",
        "export_time",
    ),
)

__all__ = ["EXAM_ENTRY_EXIT_FIELDS", "SCORE_SHEET_EXPORT_FIELDS"]
