"""Target side of ``journal_lesson_recovery`` (J12): bərpa dərsi + toqquşma sübutu.

İki hədəf yazılır, hər ikisi YALNIZ ƏLAVƏ edir — mövcud heç bir sətir
dəyişdirilmir, silinmir, üstündən yazılmır:

1. ``registrar.Lesson`` — mənbənin dərs cədvəlində OLMAYAN, amma bal xanasının
   öz ``(ay, gün, saat)`` açarından bərpa olunan dərs sətri.  Sətir
   ``is_legacy_synthesised=True`` ilə AÇIQ işarələnir və ledger-də
   ``legacy_lesson_synthesised`` kodu daşıyır — sahib onun uydurma dərs
   OLMADIĞINI, mövcud balın daşıyıcısı olduğunu bir baxışda görür.

2. ``registrar.LegacyGradeFact`` — hədəf açarı toqquşmasında UDUZAN dəyər.
   J-V4 dedup açarı ``journal_uniqid``-i daxil edir, hədəf açarı
   (``lesson``, ``enrollment``) isə etmir; 13,875 legacy jurnal hədəfdə 11,115
   açılışa BİRLƏŞİR, ona görə iki ayrı jurnalın eyni tələbə/slot xanası hədəfdə
   BİR sətrə düşür.  Dəyərlər eynidirsə itki yoxdur (27,116 xana); FƏRQLİDİRSƏ
   uduzan dəyər indiyə qədər HEÇ YERDƏ saxlanmırdı (1,633 xana).  Qalib
   DƏYİŞMİR — yalnız uduzan dəyişməz sübut qatına yazılır.

⚠️ İmtahan/təkrar imtahan (``im``/``im2``) toqquşmalarının uduzanı ARTIQ
``LegacyGradeFact``-dədir (J-facts fazası bütün ``im``/``im2`` sətirlərini
yazır), ona görə bu faza onlara TOXUNMUR — ikinci sətir ``registrar_legacy_
grade_source_uniq`` məhdudiyyətinə dəyərdi.  Onların əl ilə baxılası siyahısı
``docs/migration/BERPA_SINTETIK_DERSLER.md``-dədir.
"""

from __future__ import annotations

import datetime
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_FIELDS
from .rehearsal_authorizer import LESSON_MODEL_LABEL
from .rehearsal_journal_batch import normalized_key
from .rehearsal_journal_points_source import POINT_SOURCE_TABLE
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_lesson_recovery_conflicts import (
    CONFLICT_ALREADY_EVIDENCED_RULE_CODE,
    CONFLICT_EVIDENCE_RULE_CODE,
    CONFLICT_ISSUE_SEVERITY,
    MARK_CONFLICT_ENTITY_TYPE,
    MARK_CONFLICT_SEALER,
    ConflictFact,
    ConflictFactWriter,
    conflict_seal_key,
)
from .rehearsal_lesson_recovery_source import (
    DEFAULT_LESSON_HOURS,
    HOURS_FRACTIONAL_RULE_CODE,
    HOURS_UNRESOLVED_RULE_CODE,
)

LESSON_SYNTH_ENTITY_TYPE = "lesson_synthesised"
MARK_RECOVERY_ENTITY_TYPE = "journal_mark_recovered"
#: Bərpa olunan dərsin öz kodu — ledger-də bu dərsin MƏNBƏDƏ OLMADIĞINI deyir.
SYNTHESISED_RULE_CODE = "legacy_lesson_synthesised"
#: Xananın saatı "HH:MM" formasına düşmür (məs. legacy ``TIME`` 24 saatı aşır) —
#: dərs YARADILIR, ``start_time`` BOŞ qalır (təxmin yoxdur).
TIME_UNKNOWN_RULE_CODE = "legacy_lesson_synth_time_unknown"
#: Törədilmiş il + (ay, gün) real tarix vermir (məs. 31 noyabr) — dərs
#: yaradıla bilmir, xana KARANTİNdə qalır.
DATE_INVALID_RULE_CODE = "legacy_lesson_synth_date_invalid"
_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity
_LESSON_BATCH = 1_000

#: E-13 ilə eyni ruh: heç nə ERROR deyil — bərpa fazası tam histoqram verməlidir.
LESSON_ISSUE_SEVERITY = MappingProxyType(
    {
        # Dərsin özü mənbədə yoxdur, xanadan bərpa olundu (əsas nişan).
        SYNTHESISED_RULE_CODE: _SEVERITY.INFO,
        # Saat oxunmadı → dərs var, ``start_time`` NULL.
        TIME_UNKNOWN_RULE_CODE: _SEVERITY.WARNING,
        # Metadata sətri yoxdur / diapazondan kənardır → J3 defoltu (2 saat).
        HOURS_UNRESOLVED_RULE_CODE: _SEVERITY.INFO,
        # Vahid çevrilməsindən sonra da kəsr qaldı → J3 defoltu.
        HOURS_FRACTIONAL_RULE_CODE: _SEVERITY.WARNING,
    }
)

#: J4-ün ``ISSUE_SEVERITY``-si ilə eyni taksonomiya, ayrıca kodlarla: bərpa
#: fazasının hesabatı J4-ünkü ilə qarışmasın.
MARK_ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_journal_mark_recovered_score_out_of_range",
                "legacy_journal_mark_recovered_point_unknown",
                "legacy_journal_mark_recovered_enrollment_unresolved",
                "legacy_journal_mark_recovered_lesson_unresolved",
                "legacy_journal_mark_recovered_target_conflict",
                # Jurnal möhürü komponent toqquşmasını da sayır (C keçidi), ona
                # görə kod BURADA da xəritələnməlidir — yoxsa möhür yazılanda
                # ``legacy_rehearsal_issue_severity_unmapped`` ilə fail-closed
                # olur (2026-08-31 real-data icrasında məhz belə tutuldu).
                "legacy_journal_component_target_conflict",
                DATE_INVALID_RULE_CODE,
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                "legacy_journal_mark_recovered_orphan",
                "legacy_journal_mark_recovered_duplicate",
                "legacy_journal_mark_recovered_empty",
                "legacy_journal_mark_recovered_excused",
                "legacy_journal_mark_recovered_lab",
                "legacy_journal_archive_overlap",
                SYNTHESISED_RULE_CODE,
            ),
            _SEVERITY.INFO,
        ),
    }
)

LESSON_SYNTH_SEALER = JournalSealer(
    entity_type=LESSON_SYNTH_ENTITY_TYPE,
    source_table=POINT_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-lesson-synthesised-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=LESSON_ISSUE_SEVERITY,
)

MARK_RECOVERY_SEALER = JournalSealer(
    entity_type=MARK_RECOVERY_ENTITY_TYPE,
    source_table=POINT_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-journal-marks-recovered-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=MARK_ISSUE_SEVERITY,
)


def lesson_seal_key(*, from_archive: bool, first_cell_pk: int, group_ref: str) -> str:
    """Bərpa dərsinin möhür açarı — slotu AÇAN ilk xananın legacy sətri.

    Niyə xananın sətri: bərpa dərsinin mənbədə ÖZ sətri yoxdur, ona görə onun
    yeganə təbii legacy kimliyi onu doğuran xanadır.  Axın ciddi artan pk
    sırasındadır, «ilk» isə həmişə ən kiçik pk-dır → açar cross-run sabitdir.

    ⚠️ Cədvəl tokeni (``p``/``a``) MƏCBURİdir: əsas cədvəl və arxiv ayrı pk
    ardıcıllıqlarıdır və eyni rəqəm hər ikisində mövcuddur.  Onsuz yalnız
    arxivdən açılan slot canlı slotla eyni açara düşə bilərdi.
    """

    return f"sl:{'a' if from_archive else 'p'}:{first_cell_pk}:{group_ref}"


def mark_seal_key(uniqid: str) -> str:
    """Bərpa xanalarının jurnal-səviyyə möhürü (spec B.6 qranulyarlığı)."""

    return f"mr:{uniqid}"


@dataclass(frozen=True)
class SynthLessonRequest:
    """Bərpa olunacaq bir dərs sətri — həll bitib, hədəf pk-sı hələ yoxdur."""

    seal_key: str
    uniqid: str
    group_ref: str
    offering_pk: str
    date: datetime.date
    start_time: datetime.time | None
    kind: str
    hours: int
    topic: str
    room_pk: str
    instructor_pk: str
    first_cell_pk: int
    cell_count: int
    rule_codes: tuple[str, ...] = ()

    @property
    def slot_key(self) -> tuple[str, int, int, str]:
        """J4-ün ``lesson_slot_index`` açarı ilə eyni forma."""

        return (
            self.offering_pk,
            self.date.month,
            self.date.day,
            "" if self.start_time is None else self.start_time.isoformat(timespec="minutes"),
        )

    def digest_parts(self) -> tuple[str, ...]:
        return (
            f"journal={self.uniqid}",
            f"slice={self.group_ref}",
            f"date={self.date.isoformat()}",
            f"time={'' if self.start_time is None else self.start_time.isoformat(timespec='minutes')}",
            f"kind={self.kind}",
            f"hours={self.hours}",
            f"topic={self.topic}",
            f"room={self.room_pk}",
            f"cells={self.cell_count}",
        )


@dataclass
class SynthLessonWriter:
    """Bərpa dərslərini dəstə ilə yaradır və EYNİ tranzaksiyada möhürləyir.

    ``get_or_create`` güzgüsü: açar ``(organization, offering, date, start_time)``
    — J3-ün öz təbii açarı.  Mövcud sətir varsa (təkrar icra, və ya J3-ün
    yazdığı real dərs) HEÇ NƏ dəyişdirilmir, sətir olduğu kimi qaytarılır →
    faza idempotentdir və mövcud dərslərə toxunmur.
    """

    context: object
    #: Resume: bu run-da ARTIQ möhürlənmiş açarlar (``seal_key`` → qərar).
    recorded: dict = field(default_factory=dict)
    batch_rows: int = _LESSON_BATCH
    index: dict[tuple[str, int, int, str], tuple[str, datetime.date]] = field(default_factory=dict)
    issue_counts: Counter = field(default_factory=Counter)
    sealed: list = field(default_factory=list)
    #: Jurnal → bu run-da PLANLANMIŞ bərpa dərsi sayı (hesabat üçün).
    per_journal: Counter = field(default_factory=Counter)
    created_count: int = 0
    reused_count: int = 0
    _pending: list = field(default_factory=list)

    def add(self, request: SynthLessonRequest) -> None:
        self._pending.append(request)
        if len(self._pending) >= self.batch_rows:
            self.flush()

    def flush(self) -> None:
        """Dəstəni yaz: ƏVVƏL mövcudu tap, SONRA yalnız çatışmayanı yarat.

        İdempotentlik məhz buradadır: ikinci icrada bütün açarlar ``found``-da
        olur, ``bulk_create`` boş qalır və möhür ``already_present`` ilə SKIPPED
        yazılır — dublikat dərs struktur olaraq mümkün deyil.  Mövcud sətir
        (J3-ün yazdığı real dərs və ya əvvəlki bərpa) HEÇ CÜR dəyişdirilmir.
        """

        if not self._pending:
            return
        batch, self._pending = self._pending, []
        model = django_apps.get_model("registrar", "Lesson")
        with transaction.atomic():
            found = self._existing(model, batch)
            created: dict[tuple[str, ...], object] = {}
            for request in batch:
                key = normalized_key((request.offering_pk, request.date, request.start_time))
                if key in found or key in created:
                    continue
                created[key] = model(
                    organization=self.context.organization,
                    offering_id=request.offering_pk,
                    date=request.date,
                    start_time=request.start_time,
                    kind=request.kind,
                    hours=request.hours,
                    topic=request.topic,
                    room_id=request.room_pk or None,
                    instructor_id=request.instructor_pk or None,
                    # Import heç kimin adından yazmır.
                    created_by=None,
                    # AÇIQ NİŞAN: bu dərs mənbənin dərs cədvəlində YOXDUR.
                    is_legacy_synthesised=True,
                )
            if created:
                # ``UUIDModel`` pk-nı klientdə törədir, yəni pk ``bulk_create``-dən
                # ƏVVƏL bəllidir — ikinci axtarış sorğusu lazım deyil.
                model.objects.bulk_create(list(created.values()))
                self.created_count += len(created)
            entries = []
            for request in batch:
                key = normalized_key((request.offering_pk, request.date, request.start_time))
                row = created.get(key)
                target_pk = str(row.pk) if row is not None else found.get(key)
                if target_pk is not None:
                    # İNDEKS HƏMİŞƏ DOLUR — möhür resume-dan gəlsə belə.  Əks
                    # halda yarımçıq keçiddən sonrakı davam dərsi «tapılmadı»
                    # sayıb xanaları yazmadan keçərdi (2026-08-31-də ölçüldü).
                    self.index[request.slot_key] = (target_pk, request.date)
                previous = self.recorded.get(request.seal_key)
                if previous is not None:
                    # Möhür bu run-dadır: ikinci qərar fərqli digest törədib
                    # ledger-in kimlik konfliktinə düşərdi (J3-ün resume qapısı).
                    self.sealed.append((request.seal_key, previous))
                    continue
                if row is not None:
                    entries.append(self._entry(request, outcome="synthesised", target_pk=target_pk))
                    continue
                if target_pk is None:
                    # Nə tapıldı, nə yaradıldı → fail closed: möhür MIGRATED olmur.
                    entries.append(self._entry(request, outcome="unresolved"))
                    continue
                # Hədəf ARTIQ var (təkrar icra / J3-ün öz dərsi): dəyişdirilmir.
                self.reused_count += 1
                entries.append(self._entry(request, outcome="already_present", target_pk=target_pk))
            self._seal(entries)

    def _existing(self, model, batch) -> dict[tuple[str, ...], str]:
        dates = {request.date for request in batch}
        offerings = {request.offering_pk for request in batch}
        rows = model.objects.filter(
            organization=self.context.organization,
            offering_id__in=offerings,
            date__in=dates,
        ).values_list("pk", "offering_id", "date", "start_time")
        wanted = {normalized_key((r.offering_pk, r.date, r.start_time)) for r in batch}
        found: dict[tuple[str, ...], str] = {}
        for pk, offering_id, date, start_time in rows.iterator(chunk_size=5_000):
            key = normalized_key((offering_id, date, start_time))
            if key in wanted:
                found[key] = str(pk)
        return found

    def _entry(self, request: SynthLessonRequest, *, outcome: str, target_pk: str = "") -> JournalSealEntry:
        """Möhür: ``legacy_lesson_synthesised`` YALNIZ həqiqətən yaradılana qoyulur."""

        states = {
            "synthesised": _STATE.MIGRATED,
            "already_present": _STATE.SKIPPED,
            "unresolved": _STATE.QUARANTINED,
        }
        state = states[outcome]
        # ``legacy_map_target_by_state``: hədəf etiketi YALNIZ MIGRATED-də ola bilər.
        linked = state == _STATE.MIGRATED
        codes = (SYNTHESISED_RULE_CODE, *request.rule_codes) if outcome == "synthesised" else request.rule_codes
        return JournalSealEntry(
            seal_key=request.seal_key,
            digest=LESSON_SYNTH_SEALER.derivation_hash(
                seal_key=request.seal_key,
                outcome_token=outcome,
                parts=request.digest_parts(),
            ),
            state=state,
            label=LESSON_MODEL_LABEL if linked else "",
            target_pk=target_pk if linked else "",
            rule_codes=codes,
        )

    def _seal(self, entries) -> None:
        LESSON_SYNTH_SEALER.seal_many(self.context, entries, issue_counts=self.issue_counts)
        self.sealed.extend((entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in entries)


def same_score(stored, incoming) -> bool:
    """``LessonMark.score`` müqayisəsi — J4-ün ``_same_score`` güzgüsü."""

    if stored is None or incoming is None:
        return stored is None and incoming is None
    return Decimal(stored) == Decimal(incoming)


__all__ = [
    "CONFLICT_ALREADY_EVIDENCED_RULE_CODE",
    "CONFLICT_EVIDENCE_RULE_CODE",
    "CONFLICT_ISSUE_SEVERITY",
    "DATE_INVALID_RULE_CODE",
    "DEFAULT_LESSON_HOURS",
    "LESSON_ISSUE_SEVERITY",
    "LESSON_SYNTH_ENTITY_TYPE",
    "LESSON_SYNTH_SEALER",
    "MARK_CONFLICT_ENTITY_TYPE",
    "MARK_CONFLICT_SEALER",
    "MARK_ISSUE_SEVERITY",
    "MARK_RECOVERY_ENTITY_TYPE",
    "MARK_RECOVERY_SEALER",
    "SYNTHESISED_RULE_CODE",
    "TIME_UNKNOWN_RULE_CODE",
    "ConflictFact",
    "ConflictFactWriter",
    "SynthLessonRequest",
    "SynthLessonWriter",
    "conflict_seal_key",
    "lesson_seal_key",
    "mark_seal_key",
    "same_score",
]
