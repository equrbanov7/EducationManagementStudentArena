"""Phase: ``journal_selfwork`` (J9) — sərbəst iş MÖVZULARI → ``SelfWorkTopic``.

Niyə var (sahib şikayəti, 2026-08): jurnalın «Sərbəst iş» tabı 10 sabit sütun
göstərir və hamısı «— boş —» idi, çünki hədəfdə heç bir ``SelfWorkTopic``
yoxdu.  UI onsuz da mövzuları ``SelfWorkTopic``-dən oxuyur
(``journal_extras.get_selfwork_board``) — yəni UI DƏYİŞMİR, sadəcə data gəlir.

Nə YAZILMIR — və niyə
---------------------
``SelfWorkMark`` (mövzu-başına təhvil işarəsi) BU FAZADA YARADILMIR.  Mənbədəki
``month_id='si'`` balı (148,505 sətir) mövzu-başına deyil, (jurnal, tələbə) üzrə
TƏK aqreqat 0-10 baldır; onu 10 mövzuya "paylamaq" uydurma olardı.  Həmin bal
artıq J5-də ``AssessmentComponent(kind=self_work)`` + ``ComponentScore`` kimi
köçürülüb və BU FAZA ONA TOXUNMUR.

Nəticə (J-V12 qərarının davamı): ``gradebook_components.entry_score_for``
SELF_WORK komponenti üçün ``ComponentScore``-u DEYİL, ``SelfWorkMark`` çeklist
SAYINI oxuyur.  İşarə yazılmadığına görə say 0 qalır — yəni bu faza HEÇ BİR
tələbənin giriş balını dəyişmir.  Legacy ``si`` balı komponent bölgüsündə
görünür, mövzu siyahısı isə artıq real mətnlə dolur; ikisi bir-birini pozmur.

Mənbə qapısı
------------
``sillabus`` və ``sillabus_serbest_is`` plan-da ``design_gated``-dir, ona görə
faza onları batch zəncirinə İDDİA ETMİR (``source_tables = ()``).  Gated olmaq
iddiaya qadağadır, oxumağa yox — ``rehearsal_journal_points_source``-dakı
``archive_gated`` presedenti ilə eyni.

Sıra 45-dir: J1 (offerings, 34) açılışları qurandan sonra, J7 kilidindən (46)
əvvəl — kilid qoyulmuş jurnala mövzu yazmaq servis qatında bloklanardı.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_journal_selfwork_source import (
    SELF_WORK_SOURCE_TABLE,
    journal_syllabus_index,
    self_work_topic_index,
    syllabus_uniqid_index,
)
from .rehearsal_journal_slices import build_offering_slices
from .rehearsal_structure_phase import probe_cancellation
from .syllabus_field_contracts import SILLABUS_SELF_WORK_FIELDS

JOURNAL_SELFWORK_PHASE_KEY = "journal_selfwork"
JOURNAL_SELFWORK_PHASE_ORDER = 45  # journal_finals (44) ilə journal_lock (46) arasında
SELFWORK_ENTITY_TYPE = "journal_selfwork"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-selfwork-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_OFFERINGS_PHASE_KEY})

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_selfwork_topics_written",
        _STATE.SKIPPED: "journal_selfwork_topics_absent",
        _STATE.QUARANTINED: "journal_selfwork_unresolved",
    }
)

# E-13 ilə eyni ruh: heç nə ERROR deyil — ilk sillabus rehearsal-ı tam
# histoqram verməlidir, bloklamamalıdır.
ISSUE_SEVERITY = MappingProxyType(
    {
        # Jurnalın ``sillabus_id``-i boşdur və ya heç bir ``sillabus`` sətrinə
        # düşmür (canlı: 13,875 jurnaldan 1,824-ü).
        "legacy_selfwork_syllabus_missing": _SEVERITY.INFO,
        # Sillabus tapıldı, amma ona bağlı bir dənə də mövzu yoxdur.
        "legacy_selfwork_topics_absent": _SEVERITY.INFO,
        # Adı boş olan mövzu nömrələnmiş yer tutucu ilə köçürüldü.
        "legacy_selfwork_topic_placeholder": _SEVERITY.INFO,
        # Mövzu mətni 255 simvoldan uzun idi (canlı: 1,693 sətir) — kəsildi.
        "legacy_selfwork_title_truncated": _SEVERITY.INFO,
        # Mənbədə 10-dan çox mövzu var idi; hədəf tavanı 10-dur.
        "legacy_selfwork_topics_truncated": _SEVERITY.INFO,
        # Açılışda ARTIQ mövzu var — üstündən yazılmır (idempotentlik).
        "legacy_selfwork_topics_present": _SEVERITY.INFO,
    }
)

SELFWORK_SEALER = JournalSealer(
    entity_type=SELFWORK_ENTITY_TYPE,
    source_table=SELF_WORK_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-journal-selfwork-derivation-v1\x00",
    contract_fingerprint=SILLABUS_SELF_WORK_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def existing_topic_offerings(context, offering_pks) -> frozenset[str]:
    """Artıq mövzusu olan açılışlar — üstündən YAZILMIR (tək sorğu)."""

    model = django_apps.get_model("registrar", "SelfWorkTopic")
    rows = model.objects.filter(organization=context.organization, offering_id__in=set(offering_pks)).values_list(
        "offering_id", flat=True
    )
    return frozenset(str(pk) for pk in rows)


def write_topics(context, *, offering_pk: str, topics) -> int:
    """Mövzuları 1..N sırası ilə bir açılışa yaz.  Yalnız INSERT — heç nə yenilənmir."""

    model = django_apps.get_model("registrar", "SelfWorkTopic")
    rows = [
        model(
            organization=context.organization,
            offering_id=offering_pk,
            title=topic.title,
            order=index,
        )
        for index, topic in enumerate(topics, start=1)
    ]
    with transaction.atomic():
        model.objects.bulk_create(rows)
    return len(rows)


def decision_parts(*, syllabus_uniqid: str, topics, overflow: int, slices: int) -> tuple[str, ...]:
    """Qərarın deterministik mətn izi — mövzu mətni digest-ə TAM qatlanır."""

    return (
        f"syllabus={syllabus_uniqid}",
        f"topics={len(topics)}",
        f"overflow={overflow}",
        f"slices={slices}",
        *(f"t{index}={topic.legacy_pk}:{topic.title}" for index, topic in enumerate(topics, start=1)),
    )


def rule_codes_for(topics, *, overflow: int) -> tuple[str, ...]:
    """Bir açılışın İNFO taksonomiyası — kod başına ən çoxu bir dəfə."""

    codes: list[str] = []
    if any(topic.placeholder for topic in topics):
        codes.append("legacy_selfwork_topic_placeholder")
    if any(topic.truncated for topic in topics):
        codes.append("legacy_selfwork_title_truncated")
    if overflow:
        codes.append("legacy_selfwork_topics_truncated")
    return tuple(codes)


class JournalSelfWorkPhase:
    """J9: sillabus sərbəst iş mövzuları, jurnal başına bir möhür."""

    phase_key = JOURNAL_SELFWORK_PHASE_KEY
    order = JOURNAL_SELFWORK_PHASE_ORDER
    source_tables = ()
    entity_types = (SELFWORK_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        slices = build_offering_slices(context, migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE))
        recorded = SELFWORK_SEALER.recorded_decisions(context)
        pending = sorted(uniqid for uniqid in slices.journal_uniqids() if uniqid not in recorded)

        entries: list[JournalSealEntry] = []
        if pending:
            entries = self._plan_entries(context, slices=slices, pending=pending)

        issue_counts: Counter[tuple[str, str]] = Counter()
        SELFWORK_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        decisions = [(key, value) for key, value in recorded.items()]
        decisions.extend((entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in entries)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_SELFWORK_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    # ── Qərar qatı ──────────────────────────────────────────────────────────

    def _plan_entries(self, context, *, slices, pending) -> list[JournalSealEntry]:
        """Mənbəni üç keçidlə oxu, sonra jurnal-jurnal qərar ver."""

        syllabus_of = journal_syllabus_index(context, syllabus_of=syllabus_uniqid_index(context))
        probe_cancellation(context)
        wanted = frozenset(syllabus_of[uniqid] for uniqid in pending if uniqid in syllabus_of)
        index = self_work_topic_index(context, wanted=wanted)
        probe_cancellation(context)
        occupied = existing_topic_offerings(context, slices.offerings.values())

        entries: list[JournalSealEntry] = []
        for uniqid in pending:
            probe_cancellation(context)
            entries.append(
                self._decide(
                    context,
                    uniqid=uniqid,
                    slices=slices,
                    syllabus_uniqid=syllabus_of.get(uniqid),
                    index=index,
                    occupied=occupied,
                )
            )
        return entries

    def _decide(self, context, *, uniqid, slices, syllabus_uniqid, index, occupied) -> JournalSealEntry:
        if syllabus_uniqid is None:
            return self._empty_entry(uniqid, outcome="no_syllabus", code="legacy_selfwork_syllabus_missing")

        topics = index.for_syllabus(syllabus_uniqid)
        if not topics:
            return self._empty_entry(
                uniqid,
                outcome="no_topics",
                code="legacy_selfwork_topics_absent",
                parts=(f"syllabus={syllabus_uniqid}",),
            )

        # Sillabus JURNALındır, açılış isə DİLİMdir (``uniqid:<qrup>``) — eyni
        # mövzu siyahısı jurnalın hər materiallaşmış diliminə təkrarlanır,
        # çünki hər dilim öz jurnal səhifəsini göstərir.
        offering_pks = [slices.offerings[key] for key in slices.slice_keys(uniqid)]
        overflow = index.overflow_for(syllabus_uniqid)
        parts = decision_parts(
            syllabus_uniqid=syllabus_uniqid,
            topics=topics,
            overflow=overflow,
            slices=len(offering_pks),
        )
        targets = [pk for pk in offering_pks if pk not in occupied]
        if not targets:
            # Hər dilimdə artıq mövzu var (təkrar run və ya canlı müəllim işi) —
            # import heç vaxt akademik məzmunun üstündən yazmır.
            digest = SELFWORK_SEALER.derivation_hash(seal_key=uniqid, outcome_token="occupied", parts=parts)
            return JournalSealEntry(
                seal_key=uniqid,
                digest=digest,
                state=_STATE.SKIPPED,
                rule_codes=("legacy_selfwork_topics_present",),
            )

        digest = SELFWORK_SEALER.derivation_hash(seal_key=uniqid, outcome_token="written", parts=parts)
        for offering_pk in targets:
            write_topics(context, offering_pk=offering_pk, topics=topics)
        rule_codes = rule_codes_for(topics, overflow=overflow)
        if len(targets) != len(offering_pks):
            rule_codes = (*rule_codes, "legacy_selfwork_topics_present")
        return JournalSealEntry(
            seal_key=uniqid,
            digest=digest,
            state=_STATE.MIGRATED,
            label=COURSE_OFFERING_MODEL_LABEL,
            target_pk=slices.primary_offering(uniqid),
            rule_codes=rule_codes,
        )

    def _empty_entry(self, uniqid, *, outcome, code, parts=()) -> JournalSealEntry:
        """Yazılası bir şey yoxdur → SKIPPED + bir İNFO (karantin deyil)."""

        digest = SELFWORK_SEALER.derivation_hash(seal_key=uniqid, outcome_token=outcome, parts=parts)
        return JournalSealEntry(seal_key=uniqid, digest=digest, state=_STATE.SKIPPED, rule_codes=(code,))


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "ISSUE_SEVERITY",
    "JOURNAL_SELFWORK_PHASE_KEY",
    "JOURNAL_SELFWORK_PHASE_ORDER",
    "SELFWORK_ENTITY_TYPE",
    "JournalSelfWorkPhase",
    "decision_parts",
    "rule_codes_for",
    "write_topics",
]
