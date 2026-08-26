"""Phase: ``journal_entry_scores`` (J5b) — tarixi giriş balı üçün ARXİV komponenti.

Spec B (sahibin qərarı, 2026-08-28): «köhnə datanı silmə, pozma, dəyişmə — hər
necə hesablanıbsa hesablanıb, ballar əsas düz köçsün bura».

Nə edir
-------
Hər MATERİALLAŞMIŞ açılış (dilim) üçün BİR ``AssessmentComponent`` yaradır::

    kind = generic, name = "Davamiyyət və sərbəst iş (arxiv)", max_score = 50

və həmin açılışın HƏR yazılışına bir ``ComponentScore`` yazır.  Dəyər
``rehearsal_journal_entry_scores_source`` tərəfindən hesablanır (orada tam
əsaslandırma var): tarixi ``girish`` mənbədən (``yekun``) və ya legacy
düsturundan gəlir, komponentə isə onun kollokviumla İZAH OLUNMAYAN qalığı
yazılır — çünki ``entry_score_for`` kollokviumu HƏMİŞƏ üstəgəl edir.

Nə etmir
--------
* gündəlik xanaları, kollokvium/sərbəst iş komponentlərini VƏ onların ballarını
  NƏ silir, NƏ dəyişir — yalnız YENİ komponent əlavə olunur (spec B4);
* mövcud ``ComponentScore`` sətrinin üstündən YAZMIR (J4/J5 ilə eyni qayda:
  2 saat trigger-i yalnız ``UPDATE``-i tutur, import xalis ``INSERT`` axınıdır);
* mənbəyə YALNIZ ``yekun`` cədvəli üçün müraciət edir (spec B3-ün istisnası).

Niyə açılış-səviyyə möhür: qərar vahidi açılışdır (komponent açılışa aiddir),
yazılış sətirləri isə möhürün derivation digest-inə qatlanır — J4-J6 ilə eyni
ledger iqtisadiyyatı.  Dəyərlərin özü də digest-ə girir (``values=…``), ona görə
eyni sayda, fərqli dəyərli iki run EYNİ digest verə bilmir.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from decimal import Decimal
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import YEKUN_FIELDS
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    encoded_part,
)
from .rehearsal_journal_components_phase import JOURNAL_COMPONENTS_PHASE_KEY
from .rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE
from .rehearsal_journal_entry_scores_source import DERIVED_TOKEN, EXACT_TOKEN, build_inputs
from .rehearsal_journal_lessons_phase import journal_index
from .rehearsal_journal_marks_phase import JOURNAL_MARKS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import migrated_index
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer, state_for, tally_parts
from .rehearsal_journal_slices import enrollment_offering_index
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_ENTRY_SCORES_PHASE_KEY = "journal_entry_scores"
JOURNAL_ENTRY_SCORES_PHASE_ORDER = 43  # journal_components (42) ilə journal_finals (44) arasında
ENTRY_SCORES_ENTITY_TYPE = "journal_entry_scores"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-entry-scores-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_MARKS_PHASE_KEY, JOURNAL_COMPONENTS_PHASE_KEY})
UNATTRIBUTED_SEAL_KEY = "a-entry-score-unattributed"

# ⚠️ ``AssessmentComponent`` açarı ``(offering, name)``-dir → ad SABİTDİR.
ARCHIVE_COMPONENT_NAME = "Davamiyyət və sərbəst iş (arxiv)"
ARCHIVE_COMPONENT_KIND = "generic"
ARCHIVE_COMPONENT_MAX = 50
ARCHIVE_COMPONENT_ORDER = 0  # J5 kollokviumları 1..4-ü tutur → arxiv birinci sırada

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_entry_scores_materialised",
        _STATE.SKIPPED: "journal_entry_scores_skipped",
        _STATE.QUARANTINED: "journal_entry_scores_unresolved",
    }
)

# E-13: heç nə ERROR deyil — hesabat tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        # Dəyər ``yekun.girish``-dən gəldi — tarixi HƏQİQƏT.
        "legacy_entry_score_exact": _SEVERITY.INFO,
        # Dəyər legacy düsturu ilə bərpa olundu (``yekun`` sətri yoxdur).
        "legacy_entry_score_derived": _SEVERITY.INFO,
        # Qalıq 0..50 sərhədinə dəydi → bərpa DƏQİQ olmaya bilər.
        "legacy_entry_score_residual_clamped": _SEVERITY.WARNING,
        # Xana artıq FƏRQLİ dəyərlə mövcuddur — üstündən yazılmır.
        "legacy_entry_score_target_conflict": _SEVERITY.WARNING,
        # Ledger-də MIGRATED yazılış var, hədəfdə açılışı tapılmır.
        "legacy_entry_score_enrollment_unresolved": _SEVERITY.WARNING,
        # Açılışda ledger-dən KƏNAR yazılış var → GENERIC komponent onun giriş
        # balını sıfırlayardı; fail-closed olaraq komponent YARADILMIR.
        "legacy_entry_score_offering_incomplete": _SEVERITY.WARNING,
    }
)

OUTCOME_RULES = MappingProxyType(
    {
        "clamped": ("legacy_entry_score_residual_clamped", False),
        "conflict": ("legacy_entry_score_target_conflict", True),
        "derived": ("legacy_entry_score_derived", False),
        "exact": ("legacy_entry_score_exact", False),
        "incomplete": ("legacy_entry_score_offering_incomplete", True),
        "unresolved": ("legacy_entry_score_enrollment_unresolved", True),
    }
)
QUARANTINE_KEYS = tuple(key for key, (_code, fatal) in OUTCOME_RULES.items() if fatal)
WRITTEN_KEYS = ("written",)

ENTRY_SCORE_SEALER = JournalSealer(
    entity_type=ENTRY_SCORES_ENTITY_TYPE,
    source_table=YEKUN_FIELDS.source_table,
    derivation_prefix=b"legacy-rehearsal-journal-entry-scores-derivation-v1\x00",
    contract_fingerprint=YEKUN_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def ensure_archive_component(context, *, offering_pk: str) -> str:
    """Arxiv komponentini lazy/idempotent yarat (``(offering, name)`` unikaldır)."""

    model = django_apps.get_model("registrar", "AssessmentComponent")
    with transaction.atomic():
        component, _created = model.objects.get_or_create(
            organization=context.organization,
            offering_id=offering_pk,
            name=ARCHIVE_COMPONENT_NAME,
            defaults={
                "kind": ARCHIVE_COMPONENT_KIND,
                "max_score": ARCHIVE_COMPONENT_MAX,
                "order": ARCHIVE_COMPONENT_ORDER,
                "held_on": None,
            },
        )
    return str(component.pk)


def write_entry_score(context, *, component_pk: str, enrollment_pk: str, score) -> str:
    """``(component, enrollment)`` xanası — mövcud sətir üstündən YAZILMIR."""

    model = django_apps.get_model("registrar", "ComponentScore")
    with transaction.atomic():
        row, created = model.objects.get_or_create(
            organization=context.organization,
            component_id=component_pk,
            enrollment_id=enrollment_pk,
            defaults={"score": score, "entered_by": None},
        )
    if created:
        return "written"
    return "written" if Decimal(row.score) == Decimal(score) else "conflict"


def value_fingerprint(pairs) -> str:
    """Yazılan dəyərlərin sıra-müstəqil, deterministik barmaq izi."""

    digest = hashlib.blake2b(digest_size=16)
    for key, value in sorted(pairs):
        digest.update(encoded_part(f"{key}={value}"))
    return digest.hexdigest()


def group_enrollments(enrollments, offering_of) -> tuple[dict[str, list[tuple[str, str]]], int]:
    """``offering pk`` → sıralı ``(ledger açarı, enrollment pk)``; +həll olunmayan say.

    Bir ``Enrollment`` BİRDƏN ÇOX ledger açarı ilə göstərilə bilər (§C6: iki
    legacy jurnal eyni açılışa birləşə bilər) — o zaman ƏN KİÇİK açar seçilir,
    yəni hər yazılış siyahıda MƏHZ BİR DƏFƏ olur: təkrar yazı yoxdur və sıra
    run-dan run-a sabit qalır.
    """

    best: dict[str, dict[str, str]] = {}
    unresolved: set[str] = set()
    for ledger_key, enrollment_pk in enrollments.items():
        offering_pk = offering_of.get(enrollment_pk, "")
        if not offering_pk:
            unresolved.add(enrollment_pk)
            continue
        members = best.setdefault(offering_pk, {})
        current = members.get(enrollment_pk)
        if current is None or ledger_key < current:
            members[enrollment_pk] = ledger_key
    grouped = {offering_pk: sorted((key, pk) for pk, key in members.items()) for offering_pk, members in best.items()}
    return grouped, len(unresolved)


class JournalEntryScoresPhase:
    """J5b: tarixi giriş balının arxiv komponenti, açılış başına bir möhür."""

    phase_key = JOURNAL_ENTRY_SCORES_PHASE_KEY
    order = JOURNAL_ENTRY_SCORES_PHASE_ORDER
    source_tables = ()
    entity_types = (ENTRY_SCORES_ENTITY_TYPE,)
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

        offerings = migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE)
        enrollments = migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE)
        recorded = ENTRY_SCORE_SEALER.recorded_decisions(context)
        offering_of = enrollment_offering_index(context)
        grouped, unresolved = group_enrollments(enrollments, offering_of)
        enrolled = Counter(offering_of.values())
        inputs = build_inputs(context, journals=journal_index(context), enrollments=enrollments)

        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(recorded.items())
        entries = []
        for slice_key in sorted(offerings):
            if slice_key in recorded:
                continue
            probe_cancellation(context)
            offering_pk = offerings[slice_key]
            members = grouped.get(offering_pk, ())
            # Ledger-dən kənar yazılış varsa açılış TOXUNULMUR (fail-closed).
            incomplete = len(members) != enrolled.get(offering_pk, 0)
            entry, decision = self._decide_slice(
                context,
                seal_key=slice_key,
                offering_pk=offering_pk,
                members=() if incomplete else members,
                incomplete=incomplete,
                inputs=inputs,
            )
            entries.append(entry)
            decisions.append((slice_key, decision))
        if unresolved and UNATTRIBUTED_SEAL_KEY not in recorded:
            entry, decision = self._unattributed(unresolved)
            entries.append(entry)
            decisions.append((UNATTRIBUTED_SEAL_KEY, decision))
        ENTRY_SCORE_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_ENTRY_SCORES_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    def _decide_slice(self, context, *, seal_key: str, offering_pk: str, members, incomplete: bool, inputs):
        """Bir açılış: komponenti yarat, hər yazılışa qalığı yaz, möhürü hesabla.

        ``incomplete`` — açılışda ledger-dən kənar yazılış var: GENERIC komponent
        AÇILIŞA aid olduğuna görə belə tələbənin giriş balını sıfırlayardı, ona
        görə komponent ÜMUMİYYƏTLƏ yaradılmır (fail-closed, spec B4).
        """

        tally: Counter[str] = Counter()
        written_values: list[tuple[str, str]] = []
        if incomplete:
            tally["incomplete"] += 1
        if members:
            component_pk = ensure_archive_component(context, offering_pk=offering_pk)
            for ledger_key, enrollment_pk in members:
                value = inputs.resolve(enrollment_pk)
                tally[value.token] += 1
                if value.clamped:
                    tally["clamped"] += 1
                result = write_entry_score(
                    context, component_pk=component_pk, enrollment_pk=enrollment_pk, score=value.residual
                )
                tally[result] += 1
                if result == "written":
                    written_values.append((ledger_key, f"{value.residual}|{value.entry}"))
        state = state_for(
            written=sum(tally[key] for key in WRITTEN_KEYS),
            quarantined=sum(tally[key] for key in QUARANTINE_KEYS),
        )
        parts = (*tally_parts(tally), f"values={value_fingerprint(written_values)}")
        digest = ENTRY_SCORE_SEALER.derivation_hash(seal_key=seal_key, outcome_token=str(state), parts=parts)
        label = COURSE_OFFERING_MODEL_LABEL if state == _STATE.MIGRATED else ""
        entry = JournalSealEntry(
            seal_key=seal_key,
            digest=digest,
            state=state,
            label=label,
            target_pk=offering_pk if label else "",
            rule_codes=tuple(OUTCOME_RULES[key][0] for key in sorted(OUTCOME_RULES) if tally[key]),
        )
        return entry, (state, digest, label)

    def _unattributed(self, unresolved: int):
        """Açılışı tapılmayan yazılışlar — fail-closed görünürlük möhürü."""

        parts = (f"unresolved={unresolved}",)
        digest = ENTRY_SCORE_SEALER.derivation_hash(
            seal_key=UNATTRIBUTED_SEAL_KEY, outcome_token=str(_STATE.QUARANTINED), parts=parts
        )
        entry = JournalSealEntry(
            seal_key=UNATTRIBUTED_SEAL_KEY,
            digest=digest,
            state=_STATE.QUARANTINED,
            rule_codes=(OUTCOME_RULES["unresolved"][0],),
        )
        return entry, (_STATE.QUARANTINED, digest, "")


__all__ = [
    "ARCHIVE_COMPONENT_KIND",
    "ARCHIVE_COMPONENT_MAX",
    "ARCHIVE_COMPONENT_NAME",
    "DERIVED_DIGEST_NAMESPACE",
    "DERIVED_TOKEN",
    "ENTRY_SCORES_ENTITY_TYPE",
    "ENTRY_SCORE_SEALER",
    "EXACT_TOKEN",
    "ISSUE_SEVERITY",
    "JOURNAL_ENTRY_SCORES_PHASE_KEY",
    "JOURNAL_ENTRY_SCORES_PHASE_ORDER",
    "JournalEntryScoresPhase",
    "ensure_archive_component",
    "group_enrollments",
    "value_fingerprint",
    "write_entry_score",
]
