"""Target side of ``journal_lesson_meta`` (J11): dərs sətrinin YENİLƏNMƏSİ.

J3 dərsi YARADIR (``bulk_create``), bu faza isə mövcud sətri ZƏNGİNLƏŞDİRİR —
ona görə ``rehearsal_journal_batch.TargetMaterialiser`` (get_or_create güzgüsü)
burada uyğun gəlmir və dəstə yazıcısı ayrıca yazılıb.  İnvariantlar eynidir:
hədəf yazısı və onu hesaba alan ledger möhürü BİR ``transaction.atomic()``
içindədir, hədəf tapılmasa möhür MIGRATED olmur.

Üstünə YAZILMAYAN sahələr
-------------------------
``topic`` və ``room`` yalnız hədəfdə BOŞ olduqda yazılır (J9-un
«import heç vaxt akademik məzmunun üstündən yazmır» qaydası): müəllim mövzunu
əl ilə yazıbsa və ya otağı seçibsə, legacy dəyər onu əvəz etmir.

``hours`` isə QƏSDƏN üstündən yazılır.  Səbəb: J3 spesifikasiyaya görə HƏR
dərsə sabit ``hours=2`` qoyur, mənbədə isə dərslərin əksəriyyəti 1 saatlıqdır
(canlı ``fake=0`` bölgüsü: 0.5→3,926 · 1→175,757 · 2→85,493 · 3→30).  Bu sabit
2 saxta qayıb bloklarının kök səbəbidir, yəni düzəliş məhz köhnə dəyərin
ƏVƏZLƏNMƏSİdir.  Faza J4-dən (``journal_marks``, sıra 40) ƏVVƏL, sıra 39-da
işləyir — beləliklə J4-ün ``recompute_absence_hours`` çağırışı artıq
DÜZƏLDİLMİŞ saatları toplayır.

Kəsr saat (0.5) — qərar
-----------------------
``Lesson.hours`` ``PositiveSmallIntegerField``-dir; 0.5 ora SIĞMIR.
Yuvarlaqlaşdırma QADAĞANDIR (0.5 real dəyərdir), sahə tipini genişlətmək isə
``Enrollment.absence_hours``, ``LessonCorrection.old_hours/new_hours`` (dəyişməz
audit modeli), imtahana buraxılış qapısı və iki app-ın şablon/JSON səthlərinə
qədər yayılır — canlı dərs modalı hətta yalnız 1/2 seçimi verir.  Ona görə bu
faza kəsr sətrə saat YAZMIR: dərs J3-ün dəyəri ilə qalır və sətir
``legacy_lesson_meta_hours_fractional`` (WARNING) ilə ledger-də sayılır, yəni
sahə genişlənməsi ölçülmüş, izlənən bir qərar kimi qalır — səssiz itki yox.
Mövzu və otaq həmin sətirlərə YENƏ yazılır.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .lesson_meta_field_contracts import LESSON_ROOM_FIELDS
from .rehearsal_authorizer import LESSON_MODEL_LABEL
from .rehearsal_journal_batch import normalized_key
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_lesson_meta_source import HOURS_FRACTIONAL, HOURS_INVALID

LESSON_META_ENTITY_TYPE = "journal_lesson_meta"
LESSON_META_SOURCE_TABLE = LESSON_ROOM_FIELDS.source_table
#: Hədəf axtarışı bu qədər qərardan bir dəfə aparılır (J3 dəstəsi ilə eyni ölçü).
LESSON_META_BATCH_ROWS = 1_000

#: ``fake=1`` sətir (canlı: 26,303) — silinmiş/saxta metadata.
FAKE_RULE_CODE = "legacy_lesson_meta_fake"
#: Jurnal tapılmır və ya J1-də materiallaşmayıb (J3-ün orphan qaydası).
ORPHAN_RULE_CODE = "legacy_lesson_meta_orphan"
#: Tarix/saat qurula bilmir — QUARANTINED, heç nə yazılmır.
INVALID_RULE_CODE = "legacy_lesson_meta_invalid"
#: Eyni slot açarını 2+ metadata sətri iddia edir (canlı: 28 açar) — seçim
#: mənbədə əsaslandırıla bilmir, ona görə HEÇ BİRİ yazılmır (fail closed).
AMBIGUOUS_RULE_CODE = "legacy_lesson_meta_ambiguous"
#: Slotun dərsi hədəfdə yoxdur (J3 onu orphan/dublikat saymışdı).
LESSON_ABSENT_RULE_CODE = "legacy_lesson_meta_lesson_absent"
#: ``sillabus`` heç bir ``sillabus_sem_muh`` sətrinə düşmür / mövzu boşdur.
TOPIC_MISSING_RULE_CODE = "legacy_lesson_meta_topic_missing"
#: Mövzu 255 simvoldan uzun idi (canlı: 3,206 sətir) — kəsildi.
TOPIC_TRUNCATED_RULE_CODE = "legacy_lesson_meta_topic_truncated"
#: ``room`` 0-dır və ya silinmiş otağa istinad edir (canlı: 201 + 81 sətir).
ROOM_MISSING_RULE_CODE = "legacy_lesson_meta_room_missing"
#: Dərsdə artıq mövzu/otaq var — üstündən yazılmır (idempotentlik).
FIELD_PRESENT_RULE_CODE = "legacy_lesson_meta_field_present"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

# E-13 ilə eyni ruh: heç nə ERROR deyil — ilk metadata repetisiyası tam
# histoqram verməlidir, bloklamamalıdır.  WARNING yalnız «mənbədə dəyər VAR,
# amma hədəfə yazıla bilmədi» hallarındadır.
ISSUE_SEVERITY = MappingProxyType(
    {
        HOURS_FRACTIONAL: _SEVERITY.WARNING,
        HOURS_INVALID: _SEVERITY.WARNING,
        AMBIGUOUS_RULE_CODE: _SEVERITY.WARNING,
        INVALID_RULE_CODE: _SEVERITY.WARNING,
        **dict.fromkeys(
            (
                FAKE_RULE_CODE,
                ORPHAN_RULE_CODE,
                LESSON_ABSENT_RULE_CODE,
                TOPIC_MISSING_RULE_CODE,
                TOPIC_TRUNCATED_RULE_CODE,
                ROOM_MISSING_RULE_CODE,
                FIELD_PRESENT_RULE_CODE,
            ),
            _SEVERITY.INFO,
        ),
    }
)

LESSON_META_SEALER = JournalSealer(
    entity_type=LESSON_META_ENTITY_TYPE,
    source_table=LESSON_META_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-lesson-meta-derivation-v1\x00",
    contract_fingerprint=LESSON_ROOM_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


@dataclass(frozen=True)
class LessonMetaRequest:
    """Bir (metadata sətri × jurnal dilimi) cütünün həll olunmuş yazı niyyəti.

    Hədəf sətri hələ TAPILMAYIB: axtarış dəstə yazıcısında, bir sorğu ilə
    aparılır.  Digest-ə heç bir hədəf pk-sı girmir — cross-run determinizm J3
    ilə eyni qaydadadır.
    """

    seal_key: str
    slice_ref: str
    row_hash: str
    journal_ref: str
    offering_pk: str
    date: object
    start_time: object
    date_text: str
    time_text: str
    topic: str = ""
    room_pk: str = ""
    room_ref: str = ""
    hours: int = 0
    rule_codes: tuple[str, ...] = ()

    def digest_parts(self) -> tuple[str, ...]:
        return (
            f"row={self.row_hash}",
            f"journal={self.journal_ref}",
            f"slice={self.slice_ref}",
            f"date={self.date_text}",
            f"time={self.time_text}",
            f"topic={self.topic}",
            f"room={self.room_ref}",
            f"hours={self.hours}",
        )

    @property
    def natural_key(self) -> tuple:
        return (self.offering_pk, self.date, self.start_time)


def resolved_entry(*, seal_key: str, outcome: str, parts, rule_codes, quarantined: bool = False) -> JournalSealEntry:
    """Hədəf axtarışı LAZIM OLMAYAN qərar (fake / orphan / invalid / ambiqü)."""

    return JournalSealEntry(
        seal_key=seal_key,
        digest=LESSON_META_SEALER.derivation_hash(seal_key=seal_key, outcome_token=outcome, parts=tuple(parts)),
        state=_STATE.QUARANTINED if quarantined else _STATE.SKIPPED,
        rule_codes=tuple(rule_codes),
    )


def _lesson_model():
    return django_apps.get_model("registrar", "Lesson")


def existing_lessons(context, requests):
    """Bir dəstənin hədəf sətirləri — açar sahələri üzrə TƏK sorğu (J3 güzgüsü)."""

    keys = [request.natural_key for request in requests]
    rows = (
        _lesson_model()
        .objects.filter(
            organization=context.organization,
            offering_id__in={key[0] for key in keys},
            date__in={key[1] for key in keys},
            start_time__in={key[2] for key in keys},
        )
        .values_list("pk", "offering_id", "date", "start_time", "topic", "room_id", "hours")
    )
    wanted = {normalized_key(key) for key in keys}
    found = {}
    for row in rows.iterator(chunk_size=5_000):
        key = normalized_key(row[1:4])
        if key in wanted:
            found[key] = row
    return found


class LessonMetaWriter:
    """Qərarları buferləyir; dəstə dolanda dərsi yeniləyir və möhürləyir."""

    def __init__(self, context, *, batch_rows: int | None = None) -> None:
        self._context = context
        self._batch_rows = max(1, int(LESSON_META_BATCH_ROWS if batch_rows is None else batch_rows))
        self._pending: list[LessonMetaRequest] = []
        self._resolved: list[JournalSealEntry] = []
        self.issue_counts: Counter[tuple[str, str]] = Counter()
        self.sealed: list[tuple[str, tuple[str, str, str]]] = []

    def add(self, request: LessonMetaRequest) -> None:
        """Hədəf axtarışı TƏLƏB EDƏN qərar."""

        self._pending.append(request)
        if len(self._pending) >= self._batch_rows:
            self.flush()

    def add_resolved(self, entry: JournalSealEntry) -> None:
        """Hədəfsiz qərar; yalnız möhürlənir."""

        self._resolved.append(entry)
        if len(self._resolved) >= self._batch_rows:
            self._flush_resolved()

    def flush(self) -> None:
        self._flush_resolved()
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        with transaction.atomic():
            found = existing_lessons(self._context, batch)
            entries, updates = self._decide(batch, found)
            self._apply(updates)
            self._seal(entries)

    # ── daxili ──────────────────────────────────────────────────────────────

    def _decide(self, batch, found):
        entries: list[JournalSealEntry] = []
        # hədəf pk → [topic, room_id, hours]; CARİ dəyərlərlə başlayır ki,
        # ``bulk_update`` toxunulmayan sütunu köhnə dəyəri ilə geri yazsın.
        updates: dict[str, list] = {}
        for request in batch:
            row = found.get(normalized_key(request.natural_key))
            if row is None:
                entries.append(self._entry(request, outcome="lesson_absent", extra=(LESSON_ABSENT_RULE_CODE,)))
                continue
            target_pk, _offering, _date, _time, topic, room_id, hours = row
            values = updates.setdefault(str(target_pk), [topic, room_id, hours])
            occupied = False
            applied = False
            if request.topic:
                if (values[0] or "").strip():
                    occupied = True
                else:
                    values[0] = request.topic
                    applied = True
            if request.room_pk:
                if values[1] is not None:
                    occupied = True
                else:
                    values[1] = request.room_pk
                    applied = True
            if request.hours:
                values[2] = request.hours
                applied = True
            # MIGRATED YALNIZ mənbədən ən azı bir dəyər TƏTBİQ olunanda: mövzusu
            # da, otağı da, saatı da yazıla bilməyən sətir "yazıldı" sayılmamalıdır
            # (J9-un ``state_for`` semantikası ilə eyni).
            entries.append(
                self._entry(
                    request,
                    outcome="enriched" if applied else "noop",
                    extra=(FIELD_PRESENT_RULE_CODE,) if occupied else (),
                    target_pk=str(target_pk),
                    migrated=applied,
                )
            )
        return entries, updates

    def _apply(self, updates) -> None:
        if not updates:
            return
        model = _lesson_model()
        rows = [
            model(pk=target_pk, topic=values[0], room_id=values[1], hours=values[2])
            for target_pk, values in sorted(updates.items())
        ]
        # ``bulk_update`` ``save()``-i keçmir, yəni ``ReferenceIdentityValidationMixin``
        # işə düşmür — onsuz da ``offering_id``-ə toxunulmur və PG dəyişməzlik
        # trigger-i (``registrar_lesson``) məhz o sütunu qoruyur.
        model.objects.bulk_update(rows, ["topic", "room", "hours"], batch_size=500)

    def _entry(self, request, *, outcome, extra=(), target_pk="", migrated=False) -> JournalSealEntry:
        return JournalSealEntry(
            seal_key=request.seal_key,
            digest=LESSON_META_SEALER.derivation_hash(
                seal_key=request.seal_key,
                outcome_token=outcome,
                parts=request.digest_parts(),
            ),
            state=_STATE.MIGRATED if migrated else _STATE.SKIPPED,
            label=LESSON_MODEL_LABEL if migrated else "",
            target_pk=target_pk if migrated else "",
            rule_codes=(*request.rule_codes, *extra),
        )

    def _seal(self, entries) -> None:
        LESSON_META_SEALER.seal_many(self._context, entries, issue_counts=self.issue_counts)
        self.sealed.extend((entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in entries)

    def _flush_resolved(self) -> None:
        if not self._resolved:
            return
        entries, self._resolved = self._resolved, []
        with transaction.atomic():
            self._seal(entries)


__all__ = [
    "AMBIGUOUS_RULE_CODE",
    "FAKE_RULE_CODE",
    "FIELD_PRESENT_RULE_CODE",
    "INVALID_RULE_CODE",
    "ISSUE_SEVERITY",
    "LESSON_ABSENT_RULE_CODE",
    "LESSON_META_BATCH_ROWS",
    "LESSON_META_ENTITY_TYPE",
    "LESSON_META_SEALER",
    "LESSON_META_SOURCE_TABLE",
    "ORPHAN_RULE_CODE",
    "ROOM_MISSING_RULE_CODE",
    "TOPIC_MISSING_RULE_CODE",
    "TOPIC_TRUNCATED_RULE_CODE",
    "LessonMetaRequest",
    "LessonMetaWriter",
    "existing_lessons",
    "resolved_entry",
]
