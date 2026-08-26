"""J4/J5/J6-nın paylaşdığı xana sürücüsü: domen süzgəci + J-V4 seçkisi + J-V7 arxivi.

Üç faza EYNİ cədvəli (``journals_dates_points`` və onun arxivi) axıdır və eyni
üç mexanizmə ehtiyac duyur, ona görə mexanizm burada BİR dəfə yazılıb:

1. **Domen süzgəci** — ``month_id`` fazanın öz hədəfinə aiddirmi;
2. **J-V4 seçkisi** — qalib ``update_counter`` üzərindədir, mənbə axını isə
   PRIMARY KEY sırasındadır: qərar irəli baxış tələb edir.  ``CellElection``
   prefiltri (bit-massiv) yalnız NAMİZƏD bucket-ləri yadda saxlayır, dəqiq
   seçki isə kiçik buferdə TAM açarla aparılır — nəticə dəqiq, yaddaş sabit;
3. **J-V7 arxivi** — arxiv əsas cədvəldən SONRA axıdılır; ``added_date``
   kəsimdən sonrakı sətir idxal edilmir (overlap), əvvəlki sətir isə yalnız
   hədəf xanası hələ boşdursa yazıla bilir.

Sürücü hədəf modelini tanımır: faza ``distill`` (sətir → distillə olunmuş
xana; ``uniqid`` atributu MÜTLƏQdir) və ``decide`` (xana → yazı/hesabat)
funksiyalarını verir.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from .rehearsal_contracts import LegacyRehearsalEvidenceError
from .rehearsal_journal_offerings_source import validated_uniqid
from .rehearsal_journal_points_source import (
    ARCHIVE_CUTOFF,
    MAX_DUPLICATE_CANDIDATES,
    POINT_ARCHIVE_TABLE,
    POINT_SOURCE_TABLE,
    CellElection,
    added_on,
    archive_rows,
    cell_key,
    cell_rank,
    elect_winners,
    legacy_text,
    point_rows,
)
from .rehearsal_structure_phase import probe_cancellation

DUPLICATE_KEY = "duplicate"


MAX_JOURNAL_NOTES = 512


class JournalCellLedger:
    """Jurnal-səviyyə sətir hesabatı + resume vəziyyəti (spec B.6)."""

    __slots__ = ("cell_count", "notes", "recorded", "tallies", "touched_targets")

    def __init__(self, *, recorded) -> None:
        self.recorded = recorded
        self.tallies: dict[str, Counter[str]] = {}
        self.notes: dict[str, list[str]] = {}
        self.touched_targets: set[str] = set()
        self.cell_count = 0

    def count(self, uniqid: str, key: str) -> None:
        tally = self.tallies.get(uniqid)
        if tally is None:
            tally = self.tallies[uniqid] = Counter()
        tally[key] += 1

    def note(self, uniqid: str, text: str) -> None:
        """Sətir-səviyyə sübut mətni (J-V3 ``why``/``description``).

        Ledger-in sərbəst payload sahəsi YOXDUR (issue yalnız ``payload_digest``
        daşıyır), ona görə mətnlər OXUNAQLI saxlanılmır — jurnalın möhür
        digest-inə qatlanır: qərara hansı sənəd qeydlərinin daxil olduğu
        sübutlanır, mətnin özü isə mənbədən çıxmır.  Qapaq yaddaşı bağlayır.
        """

        bucket = self.notes.setdefault(uniqid, [])
        if len(bucket) < MAX_JOURNAL_NOTES:
            bucket.append(text)

    def evidence_part(self, uniqid: str) -> tuple[str, ...]:
        """Möhür digest-inə əlavə olunan (sırasız-sabit) sübut hissəsi."""

        bucket = self.notes.get(uniqid)
        if not bucket:
            return ()
        digest = hashlib.blake2b(digest_size=16)
        for text in sorted(bucket):
            digest.update(len(text).to_bytes(8, "big") + text.encode("utf-8", "surrogatepass"))
        return (f"evidence={len(bucket)}:{digest.hexdigest()}",)

    def total(self, keys) -> int:
        return sum(tally[key] for tally in self.tallies.values() for key in keys)


def drive_cells(context, *, ledger: JournalCellLedger, domain, distill, decide, overlap_key: str) -> None:
    """Əvvəl əsas cədvəl, sonra arxiv — J-V7 "əsas cədvəl udur" sırası."""

    for from_archive in (False, True):
        _drive_table(
            context,
            ledger=ledger,
            domain=domain,
            distill=distill,
            decide=decide,
            overlap_key=overlap_key,
            from_archive=from_archive,
        )


def _drive_table(context, *, ledger, domain, distill, decide, overlap_key, from_archive) -> None:
    table = POINT_ARCHIVE_TABLE if from_archive else POINT_SOURCE_TABLE
    election = CellElection(expected_rows=context.plan.entry_for(table).expected_rows)
    for _legacy_pk, row in _domain_rows(
        context, domain=domain, from_archive=from_archive, ledger=None, overlap_key=overlap_key
    ):
        election.observe(cell_key(row))
    probe_cancellation(context)

    pending: list[tuple[tuple, tuple[int, str, int], object]] = []
    for legacy_pk, row in _domain_rows(
        context, domain=domain, from_archive=from_archive, ledger=ledger, overlap_key=overlap_key
    ):
        cell = distill(legacy_pk, row, from_archive)
        if cell is None:
            continue
        key = cell_key(row)
        if election.is_candidate(key):
            pending.append((key, cell_rank(row, legacy_pk), cell))
            if len(pending) > MAX_DUPLICATE_CANDIDATES:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_duplicate_buffer_overflow")
            continue
        decide(cell)

    winners = elect_winners((key, rank, cell.legacy_pk) for key, rank, cell in pending)
    for key, _rank, cell in pending:
        if winners.get(key) == cell.legacy_pk:
            decide(cell)
        else:
            ledger.count(cell.uniqid, DUPLICATE_KEY)


def _domain_rows(context, *, domain, from_archive, ledger, overlap_key):
    """Fazanın domenindəki sətirlər; arxivdə üstəlik J-V7 kəsimi tətbiq olunur."""

    stream = archive_rows(context) if from_archive else point_rows(context)
    for legacy_pk, row in stream:
        probe_cancellation(context)
        if not domain(legacy_text(row["month_id"])):
            continue
        uniqid = validated_uniqid(row["journal_uniqid"])
        # Resume: möhürü artıq bu run-da olan jurnal HEÇ BİR sətri ilə yenidən
        # hesaba alınmır — ikinci möhür fərqli digest törədib ledger-in kimlik
        # konfliktinə düşərdi.
        resumed = ledger is not None and uniqid in ledger.recorded
        if from_archive:
            stamped = added_on(row)
            if stamped is None or stamped >= ARCHIVE_CUTOFF:
                if ledger is not None and not resumed:
                    ledger.count(uniqid, overlap_key)
                continue
        if resumed:
            continue
        if ledger is not None:
            ledger.cell_count += 1
        yield legacy_pk, row
