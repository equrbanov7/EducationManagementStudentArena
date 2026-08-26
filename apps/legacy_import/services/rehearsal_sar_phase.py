"""Phase: ``sar_materialisation`` — activation and the student academic record.

This is the phase that finally turns slice 1's sealed placement decision into a
row a human can see.  It accounts for NO source table (``source_tables = ()``):
``students`` is claimed by ``identity_cohort``, and reading a table another
phase claims is explicitly permitted.  Every "which group / which program does
this legacy id mean" answer is imported from ``rehearsal_placement_phase`` —
``group_index``, ``program_index``, ``student_index``, ``resolve_placement`` and
``student_rows`` — so there is exactly ONE implementation of that question and
the two phases cannot drift apart.

The placement map seals its decision as a HASH, so nothing can be read back out
of it: the phase re-derives program, group and admission year with the same
shipped functions over the same run's target state, asserts only that the
placement map exists and is SKIPPED, and folds the placement map's own
``source_row_hash`` into its derivation hash so the two evidence chains are
linked (§5.4).  This is an evidence reduction and is documented as one.

Activation is off by default: ``stage_and_activate`` (False) plus
``max_activated_accounts`` (0) are both fail-closed in ``RehearsalPolicy``, and
both are inside ``policy_digest`` — so a run that touched accounts can never
share a ``transform_version`` with one that did not.

The chain is advanced with exactly ``(legacy_pk, state, derivation_hash, label)``
per row in ascending ``legacy_pk``, where ``label`` is the SAR model label on a
MIGRATED row and ``""`` otherwise.  That is byte for byte what
``rehearsal_reconciliation._derived_phase_report_from_ledger`` rebuilds — this
phase is the first to exercise that seam with a NON-EMPTY target label.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation

from .field_contracts import STUDENT_STATUS_FIELDS
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_catalog_phase import CATALOG_PHASE_KEY, CURRICULUM_ENTITY_TYPE
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY
from .rehearsal_placement_phase import (
    PLACEMENT_ENTITY_TYPE,
    PLACEMENT_PHASE_KEY,
    group_index,
    program_index,
    resolve_placement,
    student_index,
    student_rows,
)
from .rehearsal_sar_archive import (
    ARCHIVE_EVIDENCE_SUBJECT,
    account_is_archived,
    materialise_archive,
    resolve_archive_role,
)
from .rehearsal_sar_targets import (
    SAR_ENTITY_TYPE,
    CurriculumDecision,
    RecordRequest,
    account_is_active,
    activation_evidence_digest,
    assert_activation_actor,
    materialise_record,
    resolve_curriculum,
    resolve_student_role,
    seal_deferred,
    write_issues,
)
from .rehearsal_structure_phase import STRUCTURE_PHASE_KEY, probe_cancellation
from .rehearsal_worker_targets import WORKER_MATERIALISATION_ENTITY_TYPE, migrated_observation_count
from .source_extraction import open_audited_source_stream

SAR_PHASE_KEY = "sar_materialisation"
SAR_PHASE_ORDER = 28  # after catalog (12), identity (20) and placement (25)
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-sar-phase-v1"
REQUIRED_PHASE_KEYS = frozenset({STRUCTURE_PHASE_KEY, CATALOG_PHASE_KEY, IDENTITY_PHASE_KEY, PLACEMENT_PHASE_KEY})

_STATE = LegacyEntityMap.State
_INDEX_AMBIGUOUS = "legacy_rehearsal_catalog_index_ambiguous"
_NO_CURRICULUM = CurriculumDecision("", "none", False, ())

# Token state keys, NOT migrated/skipped/quarantined: a derived decision must not
# be added to the operator-facing ``totals.{migrated,skipped,quarantined}``.
DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "sar_created",
        _STATE.SKIPPED: "sar_deferred",
        _STATE.QUARANTINED: "sar_unresolved",
    }
)


@dataclass(frozen=True)
class GroupTarget:
    """The group unit's own primary key plus the plan its provenance names."""

    target_pk: str
    curricula_legacy_pk: int


@dataclass(frozen=True)
class SarIndexes:
    """Every lookup the row loop needs, all scoped to THIS run."""

    students: Mapping[str, str]
    groups: Mapping[str, object]
    programs: Mapping[tuple[str, str], str]
    group_units: Mapping[str, GroupTarget]
    program_pks: Mapping[str, str]
    placements: Mapping[str, tuple[str, str]]
    curricula: Mapping[str, tuple[str, str]]


_NO_GROUP = GroupTarget("", 0)


def _mapping_of(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def group_target_index(context: RehearsalContext, groups) -> dict[str, GroupTarget]:
    """Slug → (unit pk, ``settings["legacy"]["curricula_id"]``).

    ``group_index`` already answered "which unit is this legacy group"; this
    only reads the two TARGET facts a SAR needs and that ``GroupPlacement``
    deliberately does not carry.
    """

    slugs = sorted({str(group.slug) for group in groups.values() if group.slug})
    index: dict[str, GroupTarget] = {}
    for row in (
        django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization=context.organization, slug__in=slugs)
        .values("id", "slug", "settings")
    ):
        legacy = _mapping_of(_mapping_of(row["settings"]).get("legacy"))
        curricula_pk = legacy.get("curricula_id")
        index[str(row["slug"])] = GroupTarget(str(row["id"]), curricula_pk if type(curricula_pk) is int else 0)
    return index


def program_pk_index(context: RehearsalContext) -> dict[str, str]:
    """``Program.code`` → primary key; the code is tenant-unique by constraint."""

    index: dict[str, str] = {}
    for row in (
        django_apps.get_model("registrar", "Program")
        .objects.filter(organization=context.organization)
        .values("id", "code")
    ):
        code = str(row["code"])
        if code in index:
            raise LegacyRehearsalEvidenceError(_INDEX_AMBIGUOUS)
        index[code] = str(row["id"])
    return index


def placement_index(context: RehearsalContext) -> dict[str, tuple[str, str]]:
    """This run's placement decisions: ``legacy_pk`` → (state, row hash)."""

    return {
        legacy_pk: (state, row_hash)
        for legacy_pk, state, row_hash in LegacyEntityObservation.objects.filter(
            run_id=context.run_id, entity_map__entity_type=PLACEMENT_ENTITY_TYPE
        ).values_list("entity_map__legacy_pk", "state", "source_row_hash")
    }


def curriculum_index(context: RehearsalContext) -> dict[str, tuple[str, str]]:
    """This run's plans: legacy ``curricula.id`` → (Curriculum pk, Program pk).

    TWO legacy keys may legitimately point at ONE ``Curriculum`` — that is the
    §5.1 merge rule — so only a repeated LEGACY key is ambiguous here.
    """

    maps = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id, state=_STATE.MIGRATED, entity_map__entity_type=CURRICULUM_ENTITY_TYPE
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    programs = {
        str(row["id"]): str(row["program_id"])
        for row in django_apps.get_model("registrar", "Curriculum")
        .objects.filter(organization=context.organization, pk__in=[target_pk for _pk, target_pk in maps])
        .values("id", "program_id")
    }
    index: dict[str, tuple[str, str]] = {}
    for legacy_pk, target_pk in maps:
        program_pk = programs.get(str(target_pk))
        if program_pk is None:
            continue  # a map whose target this tenant does not own resolves nothing
        if legacy_pk in index:
            raise LegacyRehearsalEvidenceError(_INDEX_AMBIGUOUS)
        index[legacy_pk] = (str(target_pk), program_pk)
    return index


def departed_students(context: RehearsalContext) -> frozenset[str]:
    """V-18: ``students.azadedildi == 1`` — released, and never activated.

    ``students.status`` is 0 for every live row and therefore useless; the
    release flag is the only usable source fact, and it is read through its own
    two-column contract so ``STUDENT_IDENTITY_FIELDS`` keeps its fingerprint.
    """

    entry = context.plan.entry_for(STUDENT_STATUS_FIELDS.source_table)
    departed: set[str] = set()
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=STUDENT_STATUS_FIELDS,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            if type(legacy_pk) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
            if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
            released = projected_row["azadedildi"]
            if released is not None and type(released) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
            if released == 1:
                departed.add(str(legacy_pk))
    if observed != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
    return frozenset(departed)


def build_indexes(context: RehearsalContext) -> SarIndexes:
    groups = group_index(context)
    return SarIndexes(
        students=student_index(context),
        groups=groups,
        programs=program_index(context, {group.specialty_unit_id for group in groups.values()}),
        group_units=group_target_index(context, groups),
        program_pks=program_pk_index(context),
        placements=placement_index(context),
        curricula=curriculum_index(context),
    )


def _recorded_decision(context: RehearsalContext, legacy_pk: str):
    """Resume short-circuit: replay the sealed decision instead of re-deriving."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=SAR_ENTITY_TYPE,
            entity_map__legacy_pk=legacy_pk,
        )
        .values_list("state", "source_row_hash", "target_model_label")
        .first()
    )


class SarMaterialisationPhase:
    """The activation ladder (§5.6) and the curriculum matrix (§5.5), per student."""

    phase_key = SAR_PHASE_KEY
    order = SAR_PHASE_ORDER
    source_tables = ()
    entity_types = (SAR_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, not Config: the orchestrator finishes the run FAILED with
            # this precise code instead of leaving it RUNNING.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        indexes = build_indexes(context)
        departed = departed_students(context)
        role = None
        archive_role = None
        if context.policy.stage_and_activate:
            # Both pre-flights are skipped when the switch is off: a disabled run
            # must never fail on an under-privileged actor or a missing role.
            assert_activation_actor(context)
            role = resolve_student_role(context)
            # A (arxiv üzvlüyü): məzun/xaric hesablar `alumni` rolu ilə aktiv
            # üzvlük alır — rol yoxdursa run fail-closed dayanır.
            archive_role = resolve_archive_role(context)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        issue_counts: Counter[tuple[str, str]] = Counter()
        # V-25: ``max_activated_accounts`` worker+SAR aktivasiyalarının CƏMİNƏ
        # şamildir — worker fazası (order 26) bu run-da nə istehlak edibsə,
        # büdcə oradan başlayır (SA-5 semantikası pozulmur).
        activated = migrated_observation_count(context, WORKER_MATERIALISATION_ENTITY_TYPE)
        for legacy_pk, row in student_rows(context):
            legacy_pk_text = str(legacy_pk)
            if legacy_pk_text not in indexes.students:
                continue  # not staged by this run: no map, no issue, no counter
            probe_cancellation(context)
            recorded = _recorded_decision(context, legacy_pk_text)
            if recorded is not None:
                state, digest, label = recorded
                # A resumed row that is already MIGRATED counts against the cap
                # (the 2026-08-26 finding; do not reintroduce that bug).
                activated += 1 if state == _STATE.MIGRATED else 0
            else:
                state, digest, label, promoted = self._decide(
                    context,
                    legacy_pk=legacy_pk,
                    row=row,
                    user_pk=indexes.students[legacy_pk_text],
                    indexes=indexes,
                    departed=departed,
                    role=role,
                    archive_role=archive_role,
                    activated=activated,
                    issue_counts=issue_counts,
                )
                activated += promoted
            chain.advance(legacy_pk_text, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{SAR_PHASE_KEY}.records.{sum(state_counts.values())}")
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
        self, context, *, legacy_pk, row, user_pk, indexes, departed, role, archive_role, activated, issue_counts
    ):
        """The §5.6 ladder, top to bottom; every rung seals its own ledger row."""

        legacy_pk_text = str(legacy_pk)
        recorded_placement = indexes.placements.get(legacy_pk_text)
        placement = resolve_placement(row, groups=indexes.groups, programs=indexes.programs)
        group = indexes.group_units.get(placement.group_slug, _NO_GROUP)
        program_pk = indexes.program_pks.get(placement.program_code, "")
        year_text = placement.admission_year_text
        request = RecordRequest(
            legacy_pk=legacy_pk,
            user_pk=user_pk,
            placement_row_hash="" if recorded_placement is None else recorded_placement[1],
            program_pk=program_pk,
            program_code=placement.program_code,
            group_pk=group.target_pk,
            group_slug=placement.group_slug,
            admission_year=int(year_text) if year_text else 0,
            decision=_NO_CURRICULUM,
            role=role,
            evidence_digest="",
            needs_activation=False,
        )

        if recorded_placement is None or recorded_placement[0] != _STATE.SKIPPED:
            # M6: the placement phase already issued whatever it had to say.
            return self._seal(context, request, "skipped", (), issue_counts)
        if legacy_pk_text in departed:
            # V-18 + A: buraxılmış tələbə AYRI qola düşür — hesab girişə
            # bağlı qalır, amma ARXİV üzvlüyü qurulur ki, tarixi jurnal datası
            # `registrar_guard_active_member` qapısından keçə bilsin.
            return self._decide_archive(
                context,
                request=request,
                indexes=indexes,
                role=archive_role,
                activated=activated,
                issue_counts=issue_counts,
            )
        if not year_text or not program_pk:
            # M5.  ``program_pk`` is unreachable-empty for a SKIPPED placement
            # (its state already proves the program resolved), so no issue there.
            codes = ("legacy_sar_admission_year_missing",) if not year_text else ()
            return self._seal(context, request, "skipped", codes, issue_counts)
        if not context.policy.stage_and_activate:
            # Silent by design: 7,703 identical INFO rows would be pure noise and
            # the ``sar_deferred`` count already says it.
            return self._seal(context, request, "disabled", (), issue_counts)
        if activated >= context.policy.max_activated_accounts:
            return self._seal(context, request, "capped", ("legacy_sar_activation_cap_reached",), issue_counts)

        decision = resolve_curriculum(
            context,
            program_pk=program_pk,
            group_curricula_pk=group.curricula_legacy_pk,
            curriculum_index=indexes.curricula,
        )
        request = replace_request(request, decision=decision, context=context)
        if decision.blocked:
            return self._seal(context, request, "skipped", decision.rule_codes, issue_counts)
        outcome = materialise_record(context, request=request)
        write_issues(
            context,
            legacy_pk=legacy_pk_text,
            digest=outcome.digest,
            entity_map=outcome.entity_map,
            rule_codes=(*decision.rule_codes, *outcome.rule_codes),
            issue_counts=issue_counts,
        )
        label = outcome.entity_map.target_model_label if outcome.state == _STATE.MIGRATED else ""
        return outcome.state, outcome.digest, label, 1 if outcome.state == _STATE.MIGRATED else 0

    def _decide_archive(self, context, *, request, indexes, role, activated, issue_counts):
        """A: məzun/xaric qolu — üzvlük MƏCBURİ, SAR isə şərtlidir.

        Arxiv üzvlüyü ``admission_year``/``program`` tələb ETMİR; ona görə ili
        həll olunmayan məzun da üzvlüyünü alır (jurnal datası köçür) və sətir
        ``SKIPPED`` möhürlənir — uydurulmuş akademik il yazılmır.
        """

        if not context.policy.stage_and_activate:
            # Açar bağlıdır: heç bir hesaba toxunulmur (V-18(b) davranışı).
            return self._seal(context, request, "departed", ("legacy_sar_departed_student",), issue_counts)
        if activated >= context.policy.max_activated_accounts:
            return self._seal(context, request, "capped", ("legacy_sar_activation_cap_reached",), issue_counts)

        rule_codes: tuple[str, ...] = ()
        decision = _NO_CURRICULUM
        write_record = bool(request.admission_year and request.program_pk)
        if not request.admission_year:
            rule_codes = ("legacy_sar_admission_year_missing",)
        if write_record:
            decision = resolve_curriculum(
                context,
                program_pk=request.program_pk,
                group_curricula_pk=indexes.group_units.get(request.group_slug, _NO_GROUP).curricula_legacy_pk,
                curriculum_index=indexes.curricula,
            )
            rule_codes = (*rule_codes, *decision.rule_codes)
            if decision.blocked:
                write_record = False
        request = replace_request(request, decision=decision, context=context, subject=ARCHIVE_EVIDENCE_SUBJECT)
        outcome = materialise_archive(context, request=request, role=role, write_record=write_record)
        write_issues(
            context,
            legacy_pk=str(request.legacy_pk),
            digest=outcome.digest,
            entity_map=outcome.entity_map,
            rule_codes=(*rule_codes, *outcome.rule_codes),
            issue_counts=issue_counts,
        )
        label = outcome.entity_map.target_model_label if outcome.state == _STATE.MIGRATED else ""
        # Arxivləşdirmə də HESABA toxunur → aktivasiya büdcəsindən sayılır (V-25).
        return outcome.state, outcome.digest, label, 0 if outcome.state == _STATE.QUARANTINED else 1

    def _seal(self, context, request, activation_state, rule_codes, issue_counts):
        outcome = seal_deferred(context, request=request, activation_state=activation_state, rule_codes=rule_codes)
        write_issues(
            context,
            legacy_pk=str(request.legacy_pk),
            digest=outcome.digest,
            entity_map=outcome.entity_map,
            rule_codes=outcome.rule_codes,
            issue_counts=issue_counts,
        )
        return outcome.state, outcome.digest, "", 0


def replace_request(request: RecordRequest, *, decision, context, subject: str = "student") -> RecordRequest:
    """Complete the request once the ladder decided the row really activates.

    ``subject=ARCHIVE_EVIDENCE_SUBJECT`` arxiv qoludur: «keçid lazımdırmı?»
    sualı «hesab artıq AKTİVDİRMİ?» yerinə «hesab artıq ARXİVLƏNİBMİ?» kimi
    oxunur, evidence rəqəmi də ayrı subyektlə üretilir.
    """

    if subject == ARCHIVE_EVIDENCE_SUBJECT:
        needs_transition = not account_is_archived(context, request.user_pk)
    else:
        needs_transition = not account_is_active(context, request.user_pk)
    return replace(
        request,
        decision=decision,
        needs_activation=needs_transition,
        evidence_digest=activation_evidence_digest(
            transform_version=context.policy.transform_version(),
            snapshot_sha256=context.plan.source_snapshot_sha256,
            legacy_pk=request.legacy_pk,
            subject=subject,
        ),
    )
