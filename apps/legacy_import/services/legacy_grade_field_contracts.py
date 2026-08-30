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

# ``yekun`` cədvəlinə İKİNCİ, daha geniş proyeksiya — J9-un
# ``JOURNAL_SYLLABUS_FIELDS`` presedentinin eynisi.
#
# Niyə ayrı kontrakt, niyə ``field_contracts.YEKUN_FIELDS`` genişlədilmir:
# ``YEKUN_FIELDS.fingerprint`` J5b (``journal_entry_scores``) və J8
# (``journal_reconcile``) fazalarının möhür reseptinə qatlanır və oradan hər
# ``derivation_hash``-ə düşür.  Paylaşılan kontraktı genişlətmək həmin iki
# fazanın digest-lərini dəyişər, yəni köhnə repetisiyaların ledger-i yeni kodla
# TƏKRAR TÖRƏDİLƏ BİLMƏZ.  Qiymət sübutu fazasına lazım olan beş əlavə sütun
# (``group_id``/``kesr``/``guzest_girish``/``level``/``guzest_artim``) ona görə
# burada, öz barmaq izi ilə yaşayır.
#
# Versiya adı qəsdən ``journal-*`` ailəsindən kənardır: eyni cədvələ baxan iki
# kontrakt heç vaxt eyni versiya nəsli kimi oxunmamalıdır.
YEKUN_EVIDENCE_FIELDS = LegacySourceFieldContract(
    source_table="yekun",
    version="grade-evidence-v1",
    allowed_fields=(
        "id",
        "student_id",
        "lesson_id",
        "journal_id",
        "girish",
        "imtahanda",
        "yekun",
        "group_id",
        "kesr",
        "guzest_girish",
        "level",
        "guzest_artim",
    ),
)

__all__ = [
    "EXAM_ENTRY_EXIT_FIELDS",
    "SCORE_SHEET_EXPORT_FIELDS",
    "YEKUN_EVIDENCE_FIELDS",
]
