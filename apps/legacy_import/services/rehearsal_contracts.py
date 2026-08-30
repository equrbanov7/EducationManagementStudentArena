"""Deterministic contracts, digest primitives and the attested phase registry.

Every value that enters a digest is first reduced to type-tagged text, every
failure carries a stable code and never a value, and the phase registry is
code-owned and fingerprint-attested exactly like ``load_legacy_table_plan``.

Seam contract for future adapter phases
---------------------------------------
A phase MUST emit ``PhaseBatchRecord`` items in ascending ``first_legacy_pk``
order per ``source_table`` with contiguous ``sequence`` numbers starting at 1;
MUST write its ledger rows (``upsert_entity_map`` then ``upsert_issue``) before
the batch that accounts for them; MUST NOT retain more than
``context.policy.batch_rows`` source rows simultaneously (window large tables
with ``compile_pk_chunk_query``); MUST NOT open a source connection outside
``context.source_connection_factory``; and MUST NOT call ``finish_run``.
Gated plan tables are structurally unclaimable (see ``_CLAIMABLE_ACTIONS``).

To *claim* a table means to ACCOUNT FOR it in the batch chain, not to hold an
exclusive read on it: a phase may read any audited contract through
``context.source_connection_factory``, including a table another phase claims.
A phase therefore may declare ``source_tables = ()`` — it accounts for nothing
and its evidence lives entirely in its own observations and digest chain.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from .field_contracts import LegacyProjectedRow, LegacySourceFieldContract
from .source_extraction import MAX_SOURCE_CHUNK_SIZE, LegacySourceConnection
from .table_plan import LegacyTableAction, LegacyTablePlan, load_legacy_table_plan

if TYPE_CHECKING:  # pragma: no cover - annotations only; keeps this module import-light
    from .account_cutover import AuthoritativeEmailPolicy, TargetIdentitySnapshot
    from .ledger import LedgerAuthorizer, TargetValidatorRegistry

REHEARSAL_CONTRACT_VERSION = "legacy-rehearsal-v1"
MAX_STABLE_TEXT_BYTES = 4096
SOURCE_SYSTEM = "myedu_mariadb"
TRANSFORM_FAMILY = "rehearsal-identity-v1"
DEFAULT_BATCH_ROWS = 1_000
MAX_BATCH_ROWS = 10_000
IDENTITY_COHORT_MAX_ROWS = 20_000
MAX_PHASE_KEY_LENGTH = 32
_MAX_ENTITY_TYPE_LENGTH = 64
_MAX_ROLE_NAME_LENGTH = 100
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")  # mirrors models.TOKEN_PATTERN
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_CLAIMABLE_ACTIONS = frozenset(
    {
        LegacyTableAction.TRANSFORM_CANDIDATE,
        LegacyTableAction.REVIEW_GATED,
        LegacyTableAction.VALIDATE_ONLY,
    }
)
# Pinned against the shipped registry: AcademicStructurePhase (order 10),
# AcademicCatalogPhase (12), LegacyRoomsPhase (13), IdentityCohortPhase (20),
# StudentPlacementPhase (25), WorkerMaterialisationPhase (26),
# SarMaterialisationPhase (28), JournalPeriodsPhase (32),
# JournalOfferingsPhase (34), JournalEnrollmentsPhase (36),
# JournalLessonsPhase (38), JournalLessonMetaPhase (39), JournalMarksPhase
# (40), JournalComponentsPhase (42), JournalEntryScoresPhase (43),
# JournalFinalsPhase (44), JournalSelfWorkPhase (45), JournalLockPhase (46),
# LegacyGradeFactsPhase (47), JournalReconcilePhase (48) və
# LegacyGradeArtifactsPhase (49). J9 (45) sillabus domeninin İLK fazasıdır;
# 30 rezervi jurnaldan ASILI OLMAYAN sillabus işi üçün açıq qalır (J9 açılışa
# bağlıdır, ona görə J1-dən sonra oturmalıdır).  J11 (39) QƏSDƏN J4-dən (40)
# əvvəldədir: dərs saatı düzəlməmiş ``recompute_absence_hours`` saxta qayıb
# blokları yazardı.
# Re-pin ONLY by running ``compute_phase_registry_fingerprint`` over the direct
# tuple — never over ``load_rehearsal_phase_registry``, which checks itself
# against this constant.
_EXPECTED_PHASE_REGISTRY_FINGERPRINT = "f6f2ad826a28f9fea24b552c80857554e41e3ca5334d955c3ea06dcfb9cfb0af"


class LegacyRehearsalError(Exception):
    """Sanitized rehearsal failure identified only by a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyRehearsalConfigError(LegacyRehearsalError):
    """Raised before any run row exists; the operator must fix the inputs."""


class LegacyRehearsalResumeError(LegacyRehearsalError):
    """Raised when a resumed attempt does not match the recorded scope."""


class LegacyRehearsalEvidenceError(LegacyRehearsalError):
    """Terminal-fatal: the collected evidence contradicts the fixed plan."""


class LegacyRehearsalInterrupted(LegacyRehearsalError):
    """Resumable interruption; the run is deliberately left RUNNING."""


def encoded_part(value: str) -> bytes:
    """Length-prefix one text part; mirrors ``batch_accounting._encoded_part``."""

    encoded = value.encode("utf-8", "strict")
    return len(encoded).to_bytes(8, "big") + encoded


def stable_source_value(value: object) -> str:
    """Deterministic, type-tagged text for one projected source value."""

    kind = type(value)
    if value is None:
        text = "n:"
    elif kind is bool:  # deliberately checked before int
        text = "b:1" if value else "b:0"
    elif kind is int:
        text = "i:" + str(value)
    elif kind is float:
        text = "f:" + value.hex()
    elif kind is decimal.Decimal:
        text = "d:" + format(value, "f")
    elif kind is str:
        text = "s:" + unicodedata.normalize("NFC", value)
    elif kind is bytes or kind is bytearray:
        text = "y:" + bytes(value).hex()
    elif kind is datetime.datetime:
        text = "z:" + value.isoformat()
    elif kind is datetime.date:
        text = "a:" + value.isoformat()
    elif kind is datetime.time:
        text = "c:" + value.isoformat()
    elif kind is datetime.timedelta:
        text = "e:" + str(value.total_seconds())
    else:
        # repr() could leak the value itself, so the type is never reported.
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    try:
        encoded_length = len(text.encode("utf-8", "strict"))
    except Exception:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported") from None
    if encoded_length > MAX_STABLE_TEXT_BYTES:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_too_large")
    return text


class OrderedDigest:
    """Append-only ordered hash chain; mirrors ``pk_inventory._advance_digest``."""

    __slots__ = ("_state",)

    def __init__(self, namespace: str) -> None:
        self._state = hashlib.sha256(namespace.encode("ascii")).digest()

    def advance(self, *parts: str) -> None:
        digest = hashlib.sha256(b"legacy-rehearsal-link-v1\x00")
        digest.update(self._state)
        for part in parts:
            digest.update(encoded_part(part))
        self._state = digest.digest()

    def hexdigest(self) -> str:
        return self._state.hex()

    def __repr__(self) -> str:
        return "OrderedDigest(state_length=32)"


def canonical_json_digest(payload: Mapping[str, object]) -> str:
    """Digest one JSON-safe mapping; mirrors ``table_plan._fingerprint``."""

    try:
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    except Exception:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_digest_payload_invalid") from None
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def source_row_hash(
    *,
    contract: LegacySourceFieldContract,
    legacy_pk: int,
    projected_row: LegacyProjectedRow,
) -> str:
    """Hash one projected row in fixed contract order, never row order."""

    if not isinstance(contract, LegacySourceFieldContract):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_contract_invalid")
    digest = hashlib.sha256(b"legacy-rehearsal-source-row-v1\x00")
    digest.update(encoded_part(contract.fingerprint))
    digest.update(encoded_part(contract.source_table))
    digest.update(encoded_part(str(legacy_pk)))
    for field_name in contract.allowed_fields:
        try:
            value = projected_row[field_name]
        except Exception:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_shape_invalid") from None
        digest.update(encoded_part(field_name))
        digest.update(encoded_part(stable_source_value(value)))
    return digest.hexdigest()


class UsernamePolicy(str, Enum):
    LEGACY_KEY = "legacy_key"


class StudentIdentifierPolicy(str, Enum):
    LEGACY_PK = "legacy_pk"


class EmailTrustPolicy(str, Enum):
    DENY_ALL = "deny_all"
    EVIDENCE_MANIFEST = "evidence_manifest"


class SarCurriculumFallback(str, Enum):
    STRICT = "strict"  # no legacy curriculum ⇒ no student record at all
    SYNTHESISE = "synthesise"  # mint ``Curriculum(program, admission_year)`` on demand


class PlanSemesterScheme(str, Enum):
    TERM_PAIR = "term_pair"  # payiz_N -> 2N-1, yaz_N -> 2N
    ORDINAL = "ordinal"  # payiz_N -> N,     yaz_N -> N


def _bounded_int(value: object, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _is_phase_key(value: object) -> bool:
    return type(value) is str and len(value) <= MAX_PHASE_KEY_LENGTH and bool(_TOKEN_PATTERN.fullmatch(value))


def _validated_phase_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_phase_keys_invalid")
    keys = tuple(value)
    if not keys or any(not _is_phase_key(key) for key in keys) or len(set(keys)) != len(keys):
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_phase_keys_invalid")
    return tuple(sorted(keys))


@dataclass(frozen=True, repr=False)
class RehearsalPolicy:
    """Immutable policy set; its digest seals the run's ledger scope."""

    phase_keys: tuple[str, ...]
    username_policy: UsernamePolicy
    student_identifier_policy: StudentIdentifierPolicy
    email_trust_policy: EmailTrustPolicy
    email_trust_manifest_digest: str
    batch_rows: int
    source_chunk_size: int
    max_staged_accounts: int
    student_role_name: str
    worker_role_name: str
    stage_contact_pending: bool = False
    stage_and_activate: bool = False
    max_activated_accounts: int = 0
    sar_curriculum_fallback: SarCurriculumFallback = SarCurriculumFallback.SYNTHESISE
    # V-13: in the live dump ``payiz_N``/``yaz_N`` are ordinal semester numbers,
    # so ORDINAL is the default and TERM_PAIR stays an explicit operator choice.
    plan_semester_scheme: PlanSemesterScheme = PlanSemesterScheme.ORDINAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase_keys", _validated_phase_keys(self.phase_keys))
        if (
            not isinstance(self.username_policy, UsernamePolicy)
            or not isinstance(self.student_identifier_policy, StudentIdentifierPolicy)
            or not isinstance(self.email_trust_policy, EmailTrustPolicy)
        ):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
        if self.email_trust_policy is EmailTrustPolicy.DENY_ALL:
            if self.email_trust_manifest_digest != "":
                raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")
        elif type(self.email_trust_manifest_digest) is not str or not _SHA256_PATTERN.fullmatch(
            self.email_trust_manifest_digest
        ):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")
        if not _bounded_int(self.batch_rows, minimum=1, maximum=MAX_BATCH_ROWS):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_batch_rows_invalid")
        if not _bounded_int(self.source_chunk_size, minimum=1, maximum=MAX_SOURCE_CHUNK_SIZE):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_chunk_size_invalid")
        if not _bounded_int(self.max_staged_accounts, minimum=0, maximum=IDENTITY_COHORT_MAX_ROWS):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_staging_cap_invalid")
        for role_name in (self.student_role_name, self.worker_role_name):
            if type(role_name) is not str or len(role_name) > _MAX_ROLE_NAME_LENGTH or role_name != role_name.strip():
                raise LegacyRehearsalConfigError("legacy_rehearsal_policy_role_name_invalid")
        if self.max_staged_accounts > 0 and not (self.student_role_name and self.worker_role_name):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_role_name_required")
        if type(self.stage_contact_pending) is not bool:
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
        if self.stage_contact_pending and self.max_staged_accounts == 0:
            # Düymə açıqdırsa blast-radius qapağı da açıq şəkildə verilməlidir.
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_contact_pending_invalid")
        if type(self.stage_and_activate) is not bool:
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
        if not _bounded_int(self.max_activated_accounts, minimum=0, maximum=IDENTITY_COHORT_MAX_ROWS):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_activation_invalid")
        if self.stage_and_activate and self.max_activated_accounts == 0:
            # Düymə açıqdırsa blast-radius qapağı da açıq şəkildə verilməlidir.
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_activation_invalid")
        if self.max_activated_accounts > self.max_staged_accounts:
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_activation_invalid")
        if not isinstance(self.sar_curriculum_fallback, SarCurriculumFallback):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_curriculum_fallback_invalid")
        if not isinstance(self.plan_semester_scheme, PlanSemesterScheme):
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_semester_scheme_invalid")

    def _digest_payload(self) -> dict[str, object]:
        return {
            "batch_rows": self.batch_rows,
            "email_trust_manifest_digest": self.email_trust_manifest_digest,
            "email_trust_policy": self.email_trust_policy.value,
            "max_activated_accounts": self.max_activated_accounts,
            "max_staged_accounts": self.max_staged_accounts,
            "phase_keys": list(self.phase_keys),
            "plan_semester_scheme": self.plan_semester_scheme.value,
            "sar_curriculum_fallback": self.sar_curriculum_fallback.value,
            "source_chunk_size": self.source_chunk_size,
            "stage_and_activate": self.stage_and_activate,
            "stage_contact_pending": self.stage_contact_pending,
            "student_identifier_policy": self.student_identifier_policy.value,
            "student_role_name": self.student_role_name,
            "username_policy": self.username_policy.value,
            "worker_role_name": self.worker_role_name,
        }

    def policy_digest(self) -> str:
        return canonical_json_digest(self._digest_payload())

    def transform_version(self) -> str:
        return f"{TRANSFORM_FAMILY}.{self.policy_digest()[:12]}"

    def __repr__(self) -> str:
        return (
            "RehearsalPolicy("
            f"phase_keys={self.phase_keys!r}, "
            f"email_trust_policy={self.email_trust_policy.value!r}, "
            f"batch_rows={self.batch_rows}, max_staged_accounts={self.max_staged_accounts})"
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        payload = self._digest_payload()
        payload["policy_digest"] = self.policy_digest()
        payload["transform_version"] = self.transform_version()
        return payload


@dataclass(frozen=True)
class PhaseBatchRecord:
    """Exactly the material ``record_batch`` needs, plus stable digests."""

    source_table: str
    entity_type: str
    sequence: int
    first_legacy_pk: int
    last_legacy_pk: int
    migrated_count: int
    skipped_count: int
    quarantined_count: int
    contract_fingerprint: str
    source_digest: str
    classification_digest: str
    target_digest: str


@dataclass(frozen=True)
class PhaseReport:
    """One phase's PII-free accounting result."""

    phase_key: str
    order: int
    source_tables: tuple[str, ...]
    declared_source_rows: int
    observed_source_rows: int
    batches: tuple[PhaseBatchRecord, ...]
    state_counts: Mapping[str, int]
    issue_counts: Mapping[tuple[str, str], int]
    staged_account_count: int
    phase_digest: str


@dataclass(frozen=True)
class RehearsalContext:
    """Everything a phase may use; it opens nothing of its own."""

    run_id: object
    organization: object
    actor: object
    authorize: LedgerAuthorizer
    target_validators: TargetValidatorRegistry
    policy: RehearsalPolicy
    plan: LegacyTablePlan
    source_connection_factory: Callable[[], LegacySourceConnection]
    target_identity_snapshot: TargetIdentitySnapshot
    authoritative_email_policy: AuthoritativeEmailPolicy
    cancellation_requested: Callable[[], bool]
    stdout_note: Callable[[str], None]
    # OPSİONAL sürət qatı (``ledger_batch``): etiket → "bu açarlar mövcuddur VƏ
    # tenantındır" toplu validatoru.  Verilmirsə batch yolu sətir-başına
    # ``target_validators``-a qayıdır — yəni davranış eynidir, yalnız sorğu sayı
    # dəyişir.  Etiketin ``target_validators``-da qeydiyyatı HƏR İKİ yolda
    # məcburi qalır (allowlist qapısı yumşalmır).
    bulk_target_validators: Mapping[str, object] | None = None


class RehearsalPhase(Protocol):
    """The extension seam; adapters join the registry by implementing it.

    A batch-less phase (``source_tables = ()``) MAY additionally expose two
    OPTIONAL attributes, both read with ``getattr`` by
    ``rehearsal_reconciliation._derived_phase_report_from_ledger``:

    * ``derived_digest_namespace: str`` — the ``OrderedDigest`` namespace the
      phase itself chained its rows under, so the ledger rebuild reproduces the
      live ``phase_digest`` byte for byte.
    * ``derived_state_key(state) -> str`` — the token each ledger state is
      counted under in ``state_counts``, keeping the operator-facing
      ``totals.{migrated,skipped,quarantined}`` projection unambiguous.

    Neither is part of ``compute_phase_registry_fingerprint``: they change how a
    phase's evidence is LABELLED, never what the phase is allowed to write.
    """

    phase_key: str
    order: int
    source_tables: tuple[str, ...]
    entity_types: tuple[str, ...]

    def declared_source_rows(self, plan: LegacyTablePlan) -> int: ...

    def run(self, context: RehearsalContext) -> PhaseReport: ...


def _phase_text_tuple(value: object, *, code: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise LegacyRehearsalConfigError(code)
    return tuple(value)


def validate_rehearsal_phases(phases: object, *, plan: LegacyTablePlan) -> tuple[RehearsalPhase, ...]:
    """Attest a phase registry; gated or twice-claimed tables fail closed."""

    try:
        members = tuple(phases)
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_phase_registry_invalid") from None
    if not members:
        raise LegacyRehearsalConfigError("legacy_rehearsal_phase_registry_invalid")

    seen_keys: set[str] = set()
    claimed_tables: set[str] = set()
    previous_order: int | None = None
    for phase in members:
        phase_key = getattr(phase, "phase_key", None)
        if not _is_phase_key(phase_key) or phase_key in seen_keys:
            raise LegacyRehearsalConfigError("legacy_rehearsal_phase_key_invalid")
        seen_keys.add(phase_key)
        order = getattr(phase, "order", None)
        if type(order) is not int or (previous_order is not None and order <= previous_order):
            raise LegacyRehearsalConfigError("legacy_rehearsal_phase_order_invalid")
        previous_order = order
        entity_types = _phase_text_tuple(
            getattr(phase, "entity_types", None),
            code="legacy_rehearsal_phase_entity_type_invalid",
        )
        if not entity_types or any(
            type(entity_type) is not str
            or len(entity_type) > _MAX_ENTITY_TYPE_LENGTH
            or not _TOKEN_PATTERN.fullmatch(entity_type)
            for entity_type in entity_types
        ):
            raise LegacyRehearsalConfigError("legacy_rehearsal_phase_entity_type_invalid")
        source_tables = _phase_text_tuple(
            getattr(phase, "source_tables", None),
            code="legacy_rehearsal_phase_table_unregistered",
        )
        declared_rows = 0
        for source_table in source_tables:
            try:
                entry = plan.entry_for(source_table)
            except Exception:
                raise LegacyRehearsalConfigError("legacy_rehearsal_phase_table_unregistered") from None
            if source_table in claimed_tables:
                raise LegacyRehearsalConfigError("legacy_rehearsal_phase_table_conflict")
            claimed_tables.add(source_table)
            if entry.action not in _CLAIMABLE_ACTIONS:
                raise LegacyRehearsalConfigError("legacy_rehearsal_phase_action_gated")
            if entry.adapter_key is not None:
                raise LegacyRehearsalConfigError("legacy_rehearsal_phase_adapter_key_forbidden")
            declared_rows += entry.expected_rows
        try:
            reported_rows = phase.declared_source_rows(plan)
        except Exception:
            raise LegacyRehearsalConfigError("legacy_rehearsal_phase_row_declaration_invalid") from None
        if type(reported_rows) is not int or reported_rows != declared_rows:
            raise LegacyRehearsalConfigError("legacy_rehearsal_phase_row_declaration_invalid")
    return members


def compute_phase_registry_fingerprint(
    phases: Sequence[RehearsalPhase],
    *,
    plan: LegacyTablePlan | None = None,
) -> str:
    """Fingerprint the registry shape the orchestrator is allowed to drive."""

    resolved_plan = plan if plan is not None else load_legacy_table_plan()
    payload = {
        "phases": [
            [
                phase.phase_key,
                phase.order,
                list(phase.source_tables),
                list(phase.entity_types),
                phase.declared_source_rows(resolved_plan),
            ]
            for phase in phases
        ],
        "version": REHEARSAL_CONTRACT_VERSION,
    }
    return canonical_json_digest(payload)


@lru_cache(maxsize=1)
def load_rehearsal_phase_registry() -> tuple[RehearsalPhase, ...]:
    """Load and fully attest the code-owned phase registry."""

    # Lazy: every phase module imports its types from this module.
    from .rehearsal_catalog_phase import AcademicCatalogPhase
    from .rehearsal_identity_phase import IdentityCohortPhase
    from .rehearsal_journal_components_phase import JournalComponentsPhase
    from .rehearsal_journal_enrollments_phase import JournalEnrollmentsPhase
    from .rehearsal_journal_entry_scores_phase import JournalEntryScoresPhase
    from .rehearsal_journal_finals_phase import JournalFinalsPhase
    from .rehearsal_journal_lessons_phase import JournalLessonsPhase
    from .rehearsal_journal_lock_phase import JournalLockPhase
    from .rehearsal_journal_marks_phase import JournalMarksPhase
    from .rehearsal_journal_offerings_phase import JournalOfferingsPhase
    from .rehearsal_journal_periods_phase import JournalPeriodsPhase
    from .rehearsal_journal_reconcile_phase import JournalReconcilePhase
    from .rehearsal_journal_selfwork_phase import JournalSelfWorkPhase
    from .rehearsal_legacy_grade_artifacts_phase import LegacyGradeArtifactsPhase
    from .rehearsal_legacy_grade_facts_phase import LegacyGradeFactsPhase
    from .rehearsal_lesson_meta_phase import JournalLessonMetaPhase
    from .rehearsal_lesson_rooms_phase import LegacyRoomsPhase
    from .rehearsal_placement_phase import StudentPlacementPhase
    from .rehearsal_sar_phase import SarMaterialisationPhase
    from .rehearsal_structure_phase import AcademicStructurePhase
    from .rehearsal_worker_phase import WorkerMaterialisationPhase

    plan = load_legacy_table_plan()
    # Strictly ascending ``order``: 10 structure < 12 catalog < 13 legacy_rooms
    # < 20 identity < 25 placement < 26 worker < 28 sar < 32 journal_periods
    # < 34 journal_offerings < 36 journal_enrollments < 38 journal_lessons
    # < 39 journal_lesson_meta < 40 journal_marks < 42 journal_components
    # < 43 journal_entry_scores < 44 journal_finals < 45 journal_selfwork
    # < 46 journal_lock < 47 legacy_grade_facts < 48 journal_reconcile
    # < 49 legacy_grade_artifacts
    # (30 stays reserved for the syllabus domain).
    phases = validate_rehearsal_phases(
        (
            AcademicStructurePhase(),
            AcademicCatalogPhase(),
            LegacyRoomsPhase(),
            IdentityCohortPhase(),
            StudentPlacementPhase(),
            WorkerMaterialisationPhase(),
            SarMaterialisationPhase(),
            JournalPeriodsPhase(),
            JournalOfferingsPhase(),
            JournalEnrollmentsPhase(),
            JournalLessonsPhase(),
            JournalLessonMetaPhase(),
            JournalMarksPhase(),
            JournalComponentsPhase(),
            JournalEntryScoresPhase(),
            JournalFinalsPhase(),
            JournalSelfWorkPhase(),
            JournalLockPhase(),
            LegacyGradeFactsPhase(),
            JournalReconcilePhase(),
            LegacyGradeArtifactsPhase(),
        ),
        plan=plan,
    )
    if compute_phase_registry_fingerprint(phases, plan=plan) != _EXPECTED_PHASE_REGISTRY_FINGERPRINT:
        raise LegacyRehearsalConfigError("legacy_rehearsal_phase_registry_fingerprint_mismatch")
    return phases
