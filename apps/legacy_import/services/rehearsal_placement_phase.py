"""Phase: ``student_placement`` — the durable placement decision per student.

This phase accounts for NO source table (``source_tables = ()``): ``students``
is already claimed by ``identity_cohort`` and a table may be claimed once.  It
still READS ``students`` through the very same audited contract, which makes the
recomputed ``source_row_hash`` byte-identical to the identity phase's and turns
that into a free cross-phase consistency check (D-3).

Nothing here creates a ``StudentAcademicRecord`` or a ``Curriculum``: a staged
account has an INACTIVE membership, and ``registrar_guard_active_member`` refuses
every SAR insert for it (B-1), while ``StudentAcademicRecord.curriculum`` is not
nullable and the ``curricula`` table is out of this slice (B-2).  What the phase
DOES produce is the placement decision itself — program, group unit, admission
year, degree, form, sector — sealed into a cross-run-stable
``record_derivation_hash`` that the SAR slice will consume verbatim, plus the two
target fields that carry no trigger dependency: ``UserProfile.fin`` and
``auth_user.first_name``/``last_name`` (written only when currently blank).

Evidence lives entirely in the phase's own observations and digest chain.  The
chain is advanced with exactly ``(legacy_pk, state, derivation_hash, "")`` per
row in ascending ``legacy_pk`` order, which is byte for byte what
``rehearsal_reconciliation._derived_phase_report_from_ledger`` rebuilds from the
ledger — the SA-2 hooks ``derived_digest_namespace`` and ``derived_state_key``
are what let it label that rebuild identically.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue
from core.validators import FIN_PATTERN, normalize_fin

from .field_contracts import STUDENT_IDENTITY_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .legacy_text import clean_code, clean_text
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_authorizer import USER_MODEL_LABEL
from .rehearsal_contracts import (
    IDENTITY_COHORT_MAX_ROWS,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    encoded_part,
    source_row_hash,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY, STUDENT_ENTITY_TYPE
from .rehearsal_structure_phase import GROUP_ENTITY_TYPE, STRUCTURE_PHASE_KEY, probe_cancellation
from .rehearsal_structure_source import MAX_ADMISSION_YEAR, MIN_ADMISSION_YEAR
from .source_extraction import open_audited_source_stream

PLACEMENT_PHASE_KEY = "student_placement"
PLACEMENT_PHASE_ORDER = 25  # after identity_rbac (20); leaves 30 free for syllabus
PLACEMENT_ENTITY_TYPE = "student_placement"
PLACEMENT_SOURCE_TABLE = "students"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-placement-phase-v1"
REQUIRED_PHASE_KEYS = frozenset({IDENTITY_PHASE_KEY, STRUCTURE_PHASE_KEY})
ENTRY_YEAR_PATTERN = re.compile(r"\d{4}\Z")
ENTRY_YEAR_MAX_LENGTH = 20  # students.entry_year is a varchar(20)
NAME_MAX_LENGTH = 150  # auth_user.first_name / last_name

_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State
_DERIVATION_PREFIX = b"legacy-rehearsal-placement-derivation-v1\x00"
_INDEX_AMBIGUOUS = "legacy_rehearsal_structure_index_ambiguous"
_TARGET_MISSING = "legacy_rehearsal_resume_target_missing"
_VALUE_TYPE_INVALID = "legacy_structure_source_value_type_invalid"

# Token state keys, NOT migrated/skipped/quarantined: a derived decision must not
# be added to the operator-facing ``totals.{migrated,skipped,quarantined}``,
# which ``rehearsal_report`` projects from ``_REHEARSAL_STATES`` only.
DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "record_created",  # reserved (D-6): unreachable in this slice
        _STATE.SKIPPED: "record_deferred",
        _STATE.QUARANTINED: "record_unresolved",
    }
)
_OUTCOME_TOKENS = MappingProxyType({_STATE.SKIPPED: "deferred", _STATE.QUARANTINED: "unresolved"})

# Error taxonomy (SPEC §5).  A missing key fails closed instead of defaulting to
# INFO, because an unmapped rule code would silently stop blocking a run.
ISSUE_SEVERITY = MappingProxyType(
    {
        # V-2: 2,427 live students have no admission year in ANY source, so this
        # is normal information flow and must never block a run.
        "legacy_record_admission_year_missing": _SEVERITY.INFO,
        **dict.fromkeys(
            (
                "legacy_record_group_unresolved",
                "legacy_record_program_unresolved",
                "legacy_fin_invalid_format",
                "legacy_fin_duplicate_source",
                "legacy_fin_collision",
            ),
            _SEVERITY.WARNING,
        ),
    }
)


@dataclass(frozen=True)
class GroupPlacement:
    """One migrated ``group_unit``, reduced to what a placement decision needs."""

    slug: str
    specialty_unit_id: str
    education_form: str
    sector: str
    degree_level: str
    admission_year: int | None


@dataclass(frozen=True)
class Placement:
    """The resolved decision for one student, before any target write."""

    state: str
    outcome_token: str
    program_code: str
    group_slug: str
    degree_level: str
    education_form: str
    sector: str
    admission_year_text: str
    admission_year_source: str
    rule_codes: tuple[str, ...]


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def _legacy_int(value: object) -> int:
    """A legacy integer column; ``NULL`` is the same zero sentinel MySQL writes."""

    if value is None:
        return 0
    # ``type() is int`` is already False for ``bool``, so the flags stay fatal.
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def _legacy_fin(value: object) -> str:
    """Normalise ``fincode``; a non-text column is a driver misconfiguration."""

    if value is not None and type(value) is not str:
        raise LegacyRehearsalEvidenceError(_VALUE_TYPE_INVALID)
    return normalize_fin(value)


def _mapping_of(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def student_index(context: RehearsalContext) -> dict[str, str]:
    """This run's staged students: ``legacy_pk`` → ``auth.user`` primary key."""

    rows = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            state=_STATE.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
            entity_map__entity_type=STUDENT_ENTITY_TYPE,
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    if len(rows) > IDENTITY_COHORT_MAX_ROWS:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_cohort_too_large")
    return dict(rows)


def group_index(context: RehearsalContext) -> dict[str, GroupPlacement]:
    """Group units resolved from the LEDGER, attributes read from the TARGET."""

    maps = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            state=_STATE.MIGRATED,
            entity_map__entity_type=GROUP_ENTITY_TYPE,
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    unit_model = django_apps.get_model("organizations", "OrgUnit")
    units = {
        str(row["id"]): row
        for row in unit_model.objects.filter(
            organization=context.organization, pk__in=[target_pk for _pk, target_pk in maps]
        ).values("id", "parent_id", "slug", "settings")
    }
    groups: dict[str, GroupPlacement] = {}
    claimed: set[str] = set()
    for legacy_pk, target_pk in maps:
        row = units.get(str(target_pk))
        if row is None:
            continue
        settings = _mapping_of(row["settings"])
        legacy = _mapping_of(settings.get("legacy"))
        # Two ledger keys pointing at one unit, or a unit whose own provenance
        # disagrees with the ledger, makes the placement lookup a coin toss.
        if str(target_pk) in claimed or str(legacy.get("id", legacy_pk)) != legacy_pk:
            raise LegacyRehearsalEvidenceError(_INDEX_AMBIGUOUS)
        claimed.add(str(target_pk))
        admission_year = settings.get("admission_year")
        groups[legacy_pk] = GroupPlacement(
            slug=str(row["slug"] or ""),
            specialty_unit_id=str(row["parent_id"] or ""),
            education_form=str(settings.get("education_form") or ""),
            sector=str(settings.get("sector") or ""),
            degree_level=str(settings.get("degree_level") or ""),
            admission_year=admission_year if type(admission_year) is int else None,
        )
    return groups


def program_index(context: RehearsalContext, specialty_unit_ids) -> dict[tuple[str, str], str]:
    """``(specialty_unit, degree_level)`` → program code, from the target catalogue."""

    program_model = django_apps.get_model("registrar", "Program")
    index: dict[tuple[str, str], str] = {}
    for row in program_model.objects.filter(
        organization=context.organization, specialty_unit_id__in=sorted(specialty_unit_ids)
    ).values("specialty_unit_id", "degree_level", "code"):
        key = (str(row["specialty_unit_id"]), str(row["degree_level"]))
        if key in index:
            raise LegacyRehearsalEvidenceError(_INDEX_AMBIGUOUS)
        index[key] = str(row["code"])
    return index


def _student_rows(context: RehearsalContext):
    """Stream ``students`` in attested, strictly ascending primary-key order."""

    entry = context.plan.entry_for(PLACEMENT_SOURCE_TABLE)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=STUDENT_IDENTITY_FIELDS,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            # Mirror pk_inventory._row_pk exactly: no coercion, fail closed.
            if type(legacy_pk) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
            if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
            if legacy_pk <= previous_pk:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
            previous_pk = legacy_pk
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
            yield legacy_pk, projected_row
    if observed != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")


def fin_occurrences(context: RehearsalContext) -> Counter[str]:
    """Pass 1: the FİN histogram of the WHOLE cohort and nothing else."""

    counts: Counter[str] = Counter()
    for _legacy_pk, row in _student_rows(context):
        fin = _legacy_fin(row["fincode"])
        if fin:
            counts[fin] += 1
    return counts


def _admission_year(value: object, placement: GroupPlacement | None) -> tuple[int | None, str]:
    """``entry_year`` first, then the group's ``admission_year`` (§4.5)."""

    text, _truncated = clean_code(value, max_length=ENTRY_YEAR_MAX_LENGTH)
    if ENTRY_YEAR_PATTERN.fullmatch(text) and MIN_ADMISSION_YEAR <= int(text) <= MAX_ADMISSION_YEAR:
        return int(text), "student"
    if placement is not None and placement.admission_year is not None:
        return placement.admission_year, "group"
    return None, "none"


def resolve_placement(row, *, groups, programs) -> Placement:
    """Resolve group → speciality → program; an unresolved half is quarantined."""

    rule_codes: list[str] = []
    group_legacy_pk = _legacy_int(row["group_id"])
    placement = groups.get(str(group_legacy_pk)) if group_legacy_pk else None
    program_code = ""
    if placement is None:
        rule_codes.append("legacy_record_group_unresolved")
    else:
        program_code = programs.get((placement.specialty_unit_id, placement.degree_level), "")
        if not program_code:
            rule_codes.append("legacy_record_program_unresolved")
    year, year_source = _admission_year(row["entry_year"], placement)
    if year_source == "none":
        # V-2: expected at scale — the decision stays deferred, never quarantined.
        rule_codes.append("legacy_record_admission_year_missing")
    state = _STATE.SKIPPED if placement is not None and program_code else _STATE.QUARANTINED
    return Placement(
        state=state,
        outcome_token=_OUTCOME_TOKENS[state],
        program_code=program_code,
        group_slug=placement.slug if placement is not None else "",
        degree_level=placement.degree_level if placement is not None else "",
        education_form=placement.education_form if placement is not None else "",
        sector=placement.sector if placement is not None else "",
        admission_year_text="" if year is None else str(year),
        admission_year_source=year_source,
        rule_codes=tuple(rule_codes),
    )


def record_derivation_hash(
    *, legacy_pk: int, row_hash: str, placement: Placement, fin_state: str, name_state: str
) -> str:
    """The cross-run-stable placement identity; zero UUIDs ever enter it.

    ``upsert_entity_map`` folds this into the map's canonical values, so a
    resumed attempt that derives a DIFFERENT placement is rejected by the ledger
    itself as ``legacy_entity_identity_conflict``.
    """

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        STUDENT_IDENTITY_FIELDS.fingerprint,
        str(legacy_pk),
        row_hash,
        placement.outcome_token,
        placement.program_code,
        placement.group_slug,
        placement.degree_level,
        placement.education_form,
        placement.sector,
        placement.admission_year_text,
        placement.admission_year_source,
        fin_state,
        name_state,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def _write_names(target_pk: str, first_name: str, last_name: str) -> str:
    """Fill blank names only; an existing value is never overwritten (§4.5).

    ``auth_user`` carries no trigger on these columns — 0013 guards ``OF username,
    email`` and ``OF is_active`` — so no accounts service gate applies (A-1).
    """

    users = django_apps.get_model("auth", "User")._default_manager.filter(pk=target_pk)
    row = users.values("first_name", "last_name").first()
    if row is None:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    updates = {}
    if first_name and not row["first_name"]:
        updates["first_name"] = first_name
    if last_name and not row["last_name"]:
        updates["last_name"] = last_name
    if updates:
        users.update(**updates)
        return "written"
    return "blank" if not first_name and not last_name else "preserved"


def _apply_fin(context: RehearsalContext, target_pk: str, fin: str, occurrences) -> tuple[str, tuple[str, ...]]:
    """Write the FİN inside a savepoint; every refusal leaves the field NULL."""

    if not fin:
        return "blank", ()
    if not FIN_PATTERN.fullmatch(fin):
        return "invalid", ("legacy_fin_invalid_format",)
    if occurrences.get(fin, 0) > 1:
        return "duplicate", ("legacy_fin_duplicate_source",)
    profiles = django_apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=target_pk, organization=context.organization
    )
    try:
        # Nested atomic ⇒ savepoint: a unique violation must not poison the
        # outer unit of work that still has to write the ledger row.
        with transaction.atomic():
            updated = profiles.update(fin=fin)
    except IntegrityError:
        return "collision", ("legacy_fin_collision",)
    if updated != 1:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    return "written", ()


def _write_issues(context: RehearsalContext, *, legacy_pk: str, digest: str, entity_map, rule_codes, issue_counts):
    """Issues always follow their map: the ledger rejects the other order."""

    for rule_code in rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=PLACEMENT_SOURCE_TABLE,
            entity_type=PLACEMENT_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
            severity=severity,
            payload_digest=digest,
            entity_map_id=entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1


def _recorded_decision(context: RehearsalContext, legacy_pk: str):
    """Resume short-circuit: replay the sealed decision instead of re-deriving."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=PLACEMENT_ENTITY_TYPE,
            entity_map__legacy_pk=legacy_pk,
        )
        .values_list("state", "source_row_hash")
        .first()
    )


class StudentPlacementPhase:
    """Placement decisions for the students THIS run staged; no SAR, no curriculum."""

    phase_key = PLACEMENT_PHASE_KEY
    order = PLACEMENT_PHASE_ORDER
    source_tables = ()
    entity_types = (PLACEMENT_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        # ``LegacyEntityMap.State`` has exactly these three members, so the map
        # is total and a KeyError here would mean the model itself changed.
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, not Config: the orchestrator finishes the run FAILED with
            # this precise code instead of leaving it RUNNING.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        students = student_index(context)
        groups = group_index(context)
        programs = program_index(context, {group.specialty_unit_id for group in groups.values()})
        occurrences = fin_occurrences(context)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        issue_counts: Counter[tuple[str, str]] = Counter()
        for legacy_pk, row in _student_rows(context):
            legacy_pk_text = str(legacy_pk)
            if legacy_pk_text not in students:
                continue  # not staged by this run: no map, no issue, no counter
            probe_cancellation(context)
            recorded = _recorded_decision(context, legacy_pk_text)
            if recorded is not None:
                state, digest = recorded
            else:
                state, digest = self._decide(
                    context,
                    legacy_pk=legacy_pk,
                    row=row,
                    target_pk=students[legacy_pk_text],
                    groups=groups,
                    programs=programs,
                    occurrences=occurrences,
                    issue_counts=issue_counts,
                )
            chain.advance(legacy_pk_text, str(state), digest, "")
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{PLACEMENT_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            # Only OBSERVED keys: ``_derived_phase_report_from_ledger`` rebuilds a
            # bare Counter, so a pre-seeded zero would break ``--emit-report-only``.
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _decide(
        self, context, *, legacy_pk, row, target_pk, groups, programs, occurrences, issue_counts
    ) -> tuple[str, str]:
        """Derive, write both target fields and seal the map in ONE unit of work."""

        placement = resolve_placement(row, groups=groups, programs=programs)
        row_hash = source_row_hash(contract=STUDENT_IDENTITY_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        first_name, _truncated = clean_text(row["first_name"], max_length=NAME_MAX_LENGTH)
        last_name, _truncated = clean_text(row["last_name"], max_length=NAME_MAX_LENGTH)
        fin = _legacy_fin(row["fincode"])
        legacy_pk_text = str(legacy_pk)
        with transaction.atomic():
            name_state = _write_names(target_pk, first_name, last_name)
            fin_state, fin_rules = _apply_fin(context, target_pk, fin, occurrences)
            digest = record_derivation_hash(
                legacy_pk=legacy_pk,
                row_hash=row_hash,
                placement=placement,
                fin_state=fin_state,
                name_state=name_state,
            )
            entity_map = upsert_entity_map(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                entity_type=PLACEMENT_ENTITY_TYPE,
                legacy_pk=legacy_pk_text,
                source_row_hash=digest,
                state=placement.state,
                target_model_label="",
                target_pk="",
                target_validators=context.target_validators,
            )
        _write_issues(
            context,
            legacy_pk=legacy_pk_text,
            digest=digest,
            entity_map=entity_map,
            rule_codes=(*placement.rule_codes, *fin_rules),
            issue_counts=issue_counts,
        )
        return placement.state, digest
