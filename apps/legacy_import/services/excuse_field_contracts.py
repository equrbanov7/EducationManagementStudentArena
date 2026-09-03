"""J13 (``journal_excuse_documents``) mənbə kontraktı — ``allowed_qb`` geniş.

Niyə İKİNCİ, ayrıca kontrakt (``ALLOWED_QB_FIELDS`` genişləndirilmir)
--------------------------------------------------------------------
``field_contracts.ALLOWED_QB_FIELDS`` J4-ün (``journal_marks``) işlətdiyi DAR
proyeksiyadır: ona görə cəmi dörd sütun var, çünki üzürlü-qayıb QAYDASI üçün
yalnız ``student_id`` + tarix aralığı lazımdır.  Həmin kontrakta sütun əlavə
etmək onun ``fingerprint``-ini dəyişər, o da J4-ün indiyə qədər yazdığı BÜTÜN
``source_row_hash`` dəyərlərini dəyişərdi (eyni səbəb ``STUDENT_STATUS_FIELDS``
üçün də sənədlidir).  Sənəd qatı isə mətn sütunlarını (``file``, ``desc``,
``uniq``, ``owner_id``, ``added_date``) tələb edir — ona görə burada ayrıca,
öz versiyası olan geniş kontrakt yaşayır.  İki kontraktın eyni cədvəli oxuması
icazəlidir: "iddia" (claim) batch mühasibatına aiddir, oxumağa yox
(``rehearsal_contracts`` seam qeydi).

``desc`` MariaDB-də açar sözdür; proyeksiya identifikatorları backtick ilə
sitat gətirdiyi üçün (``LegacySafeProjection.select_sql``) əlavə tədbir
lazım deyil.

⚠️ Bu modul QƏSDƏN import-yüngüldür (yalnız ``field_contracts``): onu
``source_extraction`` audited allowlist-i idxal edir, ona görə burada
``rehearsal_contracts``-a istinad SİKL yaradardı.  Digest resepti ona görə
``rehearsal_excuse_documents``-dədir (``legacy_grade_artifact_contracts``
presedenti ilə eyni bölgü).
"""

from __future__ import annotations

from .field_contracts import ALLOWED_QB_FIELDS, LegacySourceFieldContract

#: Sənəd qatının geniş proyeksiyası — mənbənin BÜTÜN doqquz sütunu.
ALLOWED_QB_DOCUMENT_FIELDS = LegacySourceFieldContract(
    source_table="allowed_qb",
    version="excuse-v1",
    allowed_fields=(
        "id",
        "owner_id",
        "student_id",
        "allowed_date_start",
        "allowed_date_end",
        "file",
        "added_date",
        "desc",
        "uniq",
    ),
)

#: (dar J4 kontraktı, geniş sənəd kontraktı) — sintetik fixture cədvəli
#: GENİŞ olanla qurulmalıdır, əks halda geniş oxucu
#: ``legacy_source_schema_contract_mismatch`` ilə çökür (``yekun`` tələsi).
EXCUSE_SUPERSET_INVARIANTS = ((ALLOWED_QB_FIELDS, ALLOWED_QB_DOCUMENT_FIELDS),)

__all__ = [
    "ALLOWED_QB_DOCUMENT_FIELDS",
    "EXCUSE_SUPERSET_INVARIANTS",
]
