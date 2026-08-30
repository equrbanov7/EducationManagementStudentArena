"""Phase: ``legacy_rooms`` (J10) — ``rooms`` → ``exams.ExamRoom`` reyestri.

Niyə var (sahib şikayəti, 2026-08-30): köhnə sistemdə hər dərsə OTAQ və KORPUS
yazılırdı, hədəfdə isə 293,070 dərsin hamısında ``room_id`` boşdur.  Otağı
dərsə bağlamaq üçün əvvəlcə otağın ÖZÜ hədəfdə olmalıdır — bu faza məhz onu
qurur, dərs bağlantısını isə J11 (``journal_lesson_meta``) edir.

Niyə ``exams.ExamRoom``
-----------------------
``registrar.Lesson.room`` FK-sı (miqrasiya 0051) məhz ona baxır və modelin öz
şərhi səbəbi yazır: təşkilatın YEGANƏ otaq reyestri odur (org-scoped,
``building``/``floor``/``capacity`` sahələri və hazır CRUD ekranı ilə).  Model
``django.apps.get_model`` ilə həll olunur — ``legacy_import → exams`` Python
idxal tili YARANMIR (``rehearsal_authorizer`` ilə eyni qayda).

Legacy açar
-----------
``code = "myedu-room-<legacy id>"`` (``legacy_text.legacy_slug`` forması, 32
simvolluq sütuna sığır) və ``ExamRoom`` unikallığı məhz ``(organization, code)``
üzərindədir — yəni faza təkrar işləyəndə eyni sətir tapılır, dublikat yaranmır.
Otaq ADI unikal DEYİL (canlı: 158 otaqdan 25-i ad təkrarı, 8-i hətta eyni
korpusda), ona görə kimlik ADDAN qurula bilməzdi.

Korpus formatı — qərar
----------------------
``rooms.bina`` ``int(1)``-dir (canlı bölgü 1→43, 2→57, 3→44, 5→14 otaq), hədəf
``ExamRoom.building`` isə mətndir.  Yazılan dəyər tam ədədin ONLUQ MƏTNİdir
("1", "2", "3", "5") — "3-cü korpus" DEYİL.  Üç səbəb:

* jurnalın dərs modalında (``registrar/partials/_jd_lesson_modal.html``) sahənin
  öz etiketi artıq «KORPUS»-dur və seçim dəyəri hərfi-hərfinə göstərilir —
  "3-cü korpus" orada «KORPUS: 3-cü korpus» kimi oxunardı;
* ``lesson_rooms.lesson_building_choices`` siyahını MƏTN kimi sıralayır; tək
  rəqəmlər düzgün sıralanır və sonradan "4" əlavə olunsa da sıra pozulmur;
* mənbə sütunu tam ədəddir: onluq mətn eyniyyət çevirməsidir, hər hansı başqa
  forma isə DATA sahəsinə təqdimat mətni uydurmaq olardı (təqdimat şablonun
  işidir).  İmtahan mərkəzi ``ExamRoomForm`` ilə korpusu sonradan istədiyi kimi
  adlandıra bilər — bu, ən az fikir yürüdən başlanğıc dəyərdir.

Sıra 13-dür: akademik struktur (10) və kataloq (12) fazalarından sonra, kimlik
(20) fazasından əvvəl.  Otaq reyestri heç bir jurnaldan asılı deyil, ona görə
jurnal zəncirinin qabağında oturur və J11 onu hazır tapır.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .legacy_text import clean_text
from .lesson_meta_field_contracts import ROOM_REGISTRY_FIELDS
from .rehearsal_authorizer import EXAM_ROOM_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_lesson_meta_source import ROOM_NAME_MAX_LENGTH, legacy_calendar_int, room_registry_rows
from .rehearsal_structure_phase import probe_cancellation

LEGACY_ROOMS_PHASE_KEY = "legacy_rooms"
LEGACY_ROOMS_PHASE_ORDER = 13  # academic_catalog (12) ilə identity_cohort (20) arasında
LEGACY_ROOM_ENTITY_TYPE = "legacy_room"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-legacy-rooms-v1"
ROOM_CODE_PREFIX = "myedu-room-"
#: ``ExamRoom.capacity`` ``PositiveIntegerField``-dir; legacy ``max_student_count``
#: ``char(2)``-dir, yəni ən çoxu iki rəqəm.
MAX_ROOM_CAPACITY = 999

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "legacy_room_materialised",
        _STATE.SKIPPED: "legacy_room_skipped",
        _STATE.QUARANTINED: "legacy_room_unresolved",
    }
)

# E-13 ilə eyni ruh: heç nə ERROR deyil — ilk otaq repetisiyası tam histoqram
# verməlidir, bloklamamalıdır.
ISSUE_SEVERITY = MappingProxyType(
    {
        # Otaq adı 120 simvoldan uzun idi (canlı: yoxdur, ən uzunu 14) — kəsildi.
        "legacy_room_name_truncated": _SEVERITY.INFO,
        # ``max_student_count`` rəqəm deyil / diapazondan kənardır → tutum 0.
        "legacy_room_capacity_invalid": _SEVERITY.INFO,
        # Adı boş olan otaq legacy kodu ilə adlandırıldı.
        "legacy_room_name_placeholder": _SEVERITY.INFO,
    }
)

ROOM_SEALER = JournalSealer(
    entity_type=LEGACY_ROOM_ENTITY_TYPE,
    source_table=ROOM_REGISTRY_FIELDS.source_table,
    derivation_prefix=b"legacy-rehearsal-legacy-room-derivation-v1\x00",
    contract_fingerprint=ROOM_REGISTRY_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def room_code(legacy_pk: int) -> str:
    """Legacy açarlı otaq kodu; ad təkrarlarına görə kimlik ADDAN qurulmur."""

    if type(legacy_pk) is not int or legacy_pk < 1:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return f"{ROOM_CODE_PREFIX}{legacy_pk}"


def room_capacity(value: object) -> tuple[int, str]:
    """``max_student_count`` (``char(2)``) → ``(tutum, issue kodu)``."""

    if type(value) is int and 0 <= value <= MAX_ROOM_CAPACITY:
        return value, ""
    if type(value) is str:
        text = value.strip()
        if text.isdigit() and len(text) <= 3:
            capacity = int(text)
            if capacity <= MAX_ROOM_CAPACITY:
                return capacity, ""
    return 0, "legacy_room_capacity_invalid"


class LegacyRoomDecision:
    """Bir legacy otaq sətrinin tam həll olunmuş hədəf forması."""

    __slots__ = ("legacy_pk", "code", "name", "building", "capacity", "rule_codes")

    def __init__(self, *, legacy_pk: int, row) -> None:
        name, truncated = clean_text(row["name"], max_length=ROOM_NAME_MAX_LENGTH)
        capacity, capacity_code = room_capacity(row["max_student_count"])
        codes: list[str] = []
        self.legacy_pk = legacy_pk
        self.code = room_code(legacy_pk)
        if not name:
            name = self.code
            codes.append("legacy_room_name_placeholder")
        if truncated:
            codes.append("legacy_room_name_truncated")
        if capacity_code:
            codes.append(capacity_code)
        self.name = name
        # KORPUS: tam ədədin onluq mətni (modul qeydindəki qərar).
        self.building = str(legacy_calendar_int(row["bina"]))
        self.capacity = capacity
        self.rule_codes = tuple(codes)

    def digest_parts(self) -> tuple[str, ...]:
        return (
            f"code={self.code}",
            f"name={self.name}",
            f"building={self.building}",
            f"capacity={self.capacity}",
        )


def materialise_rooms(context: RehearsalContext, decisions) -> dict[str, str]:
    """Otaqları legacy kod üzrə idempotent təmin et; kod → hədəf pk qaytarır.

    Mövcud sətrin ADI/KORPUSU ÜSTÜNDƏN YAZILMIR: imtahan mərkəzi otağı sonradan
    adlandıra bilər və import heç vaxt insan işinin üstünə yazmır (J9 qaydası).
    """

    model = django_apps.get_model("exams", "ExamRoom")
    wanted = {decision.code: decision for decision in decisions}
    if not wanted:
        return {}
    with transaction.atomic():
        found = {
            code: str(pk)
            for pk, code in model.objects.filter(
                organization=context.organization, code__in=sorted(wanted)
            ).values_list("pk", "code")
        }
        missing = [wanted[code] for code in sorted(wanted) if code not in found]
        if missing:
            created = [
                model(
                    organization=context.organization,
                    code=decision.code,
                    name=decision.name,
                    building=decision.building,
                    capacity=decision.capacity,
                    is_active=True,
                )
                for decision in missing
            ]
            model.objects.bulk_create(created)
            found.update({decision.code: str(row.pk) for decision, row in zip(missing, created)})
    return found


class LegacyRoomsPhase:
    """J10: legacy otaq reyestri → ``exams.ExamRoom`` (sətir başına bir möhür)."""

    phase_key = LEGACY_ROOMS_PHASE_KEY
    order = LEGACY_ROOMS_PHASE_ORDER
    source_tables = ()
    entity_types = (LEGACY_ROOM_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    derived_ledger_sort_key = staticmethod(int)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        probe_cancellation(context)

        recorded = ROOM_SEALER.recorded_decisions(context)
        decisions = [
            LegacyRoomDecision(legacy_pk=legacy_pk, row=row)
            for legacy_pk, row in room_registry_rows(context)
            if str(legacy_pk) not in recorded
        ]
        probe_cancellation(context)
        targets = materialise_rooms(context, decisions)

        entries: list[JournalSealEntry] = []
        for decision in decisions:
            target_pk = targets.get(decision.code, "")
            if not target_pk:
                # Hədəf yaradıla bilmədisə möhür yalançı olardı — fail closed.
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_target_unresolved")
            entries.append(
                JournalSealEntry(
                    seal_key=str(decision.legacy_pk),
                    digest=ROOM_SEALER.derivation_hash(
                        seal_key=str(decision.legacy_pk),
                        outcome_token="materialised",
                        parts=decision.digest_parts(),
                    ),
                    state=_STATE.MIGRATED,
                    label=EXAM_ROOM_MODEL_LABEL,
                    target_pk=target_pk,
                    rule_codes=decision.rule_codes,
                )
            )

        issue_counts: Counter[tuple[str, str]] = Counter()
        ROOM_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        sealed = list(recorded.items())
        sealed.extend((entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in entries)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(sealed, key=lambda item: int(item[0])):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{LEGACY_ROOMS_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "ISSUE_SEVERITY",
    "LEGACY_ROOMS_PHASE_KEY",
    "LEGACY_ROOMS_PHASE_ORDER",
    "LEGACY_ROOM_ENTITY_TYPE",
    "ROOM_CODE_PREFIX",
    "ROOM_SEALER",
    "LegacyRoomDecision",
    "LegacyRoomsPhase",
    "materialise_rooms",
    "room_capacity",
    "room_code",
]
