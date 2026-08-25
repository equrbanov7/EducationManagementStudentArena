"""Orchestrator tests (SPEC §15.1/34-43).

Everything runs on SQLite: the source preflight and the MariaDB factory are
injected, the target guard is patched, and ``load_legacy_table_plan`` is
replaced by the shrunken two-table plan the identity-phase tests already use.
The real source attestation, ledger, batch chain and report writer all run.
"""

import hashlib
import json
from collections import Counter
from types import SimpleNamespace

from django.contrib.auth import get_user_model

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services import rehearsal_orchestrator as orchestrator
from apps.legacy_import.services import rehearsal_phase_a as phase_a_module
from apps.legacy_import.services.account_cutover import EmailTrustDecision
from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
from apps.legacy_import.services.ledger import upsert_entity_map
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    LegacyRehearsalResumeError,
    OrderedDigest,
    PhaseReport,
)
from apps.legacy_import.services.rehearsal_identity_phase import IdentityCohortPhase
from apps.legacy_import.services.rehearsal_orchestrator import (
    cancel_rehearsal,
    execute_rehearsal,
    plan_rehearsal,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger, reconcile_run
from apps.legacy_import.services.rehearsal_report import REPORT_NAME_TEMPLATE
from apps.legacy_import.services.rehearsal_target_guard import TargetGuardAttestation
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256
from apps.legacy_import.tests.test_rehearsal_identity_phase import _factory, _plan, _policy, _row
from apps.organizations.models import Organization
from core.constants import OrganizationType

_SOURCE_PATH = "/nonexistent/legacy-snapshot.sql"
_SOURCE_SIZE_BYTES = 2_142_912_818
_STUDENT_ROWS = 3
_WORKER_ROWS = 2

_GUARD = TargetGuardAttestation(
    vendor="postgresql",
    database_name_shape="emsarena_rehearsal_<12hex>",
    loopback=True,
    non_default_port=True,
    disposable_marker=True,
    role_is_superuser=False,
    role_bypasses_rls=False,
    rls_bypass_active=False,
    migration_head_digest="e" * 64,
)


def _preflight(**_kwargs):
    return SimpleNamespace(digest=SOURCE_SNAPSHOT_SHA256, size=_SOURCE_SIZE_BYTES)


def _source_rows(students=_STUDENT_ROWS, workers=_WORKER_ROWS):
    return {
        "students": [
            _row(STUDENT_IDENTITY_FIELDS, index, email=f"student-{index}@example.test")
            for index in range(1, students + 1)
        ],
        "workers": [
            _row(WORKER_IDENTITY_FIELDS, index, email=f"worker-{index}@example.test") for index in range(1, workers + 1)
        ],
    }


def build_rehearsal_target(monkeypatch, tmp_path):
    """Patch the plan, the target guard and the disposable-name confirmation.

    Shared with ``test_rehearsal_postgres`` so both suites drive the identical
    shrunken two-table plan and the identical guard attestation.
    """

    plan = _plan(students=_STUDENT_ROWS, workers=_WORKER_ROWS)
    monkeypatch.setattr(phase_a_module, "load_legacy_table_plan", lambda: plan)
    monkeypatch.setattr(phase_a_module, "assert_disposable_rehearsal_target", lambda **_kwargs: _GUARD)
    monkeypatch.setattr(orchestrator, "assert_disposable_rehearsal_target", lambda **_kwargs: _GUARD)
    monkeypatch.setattr(orchestrator, "_assert_apply_confirmation", lambda _value: None)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    return SimpleNamespace(plan=plan, report_dir=str(report_dir))


@pytest.fixture()
def rehearsal_target(db, monkeypatch, tmp_path):
    return build_rehearsal_target(monkeypatch, tmp_path)


def _organization(code):
    owner = get_user_model().objects.create_superuser(
        username=f"rehearsal_orch_{code}",
        email=f"rehearsal-orch-{code}@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name=f"Rehearsal Orchestrator {code.title()}",
        slug=f"rehearsal-orchestrator-{code}",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    return organization, owner


def _cancel_after_first_batch():
    """Arm the phase-level interlock only once a whole window has been sealed.

    ``open_audited_identity_stream`` polls the same callable per row, so a naive
    counter would abort mid-stream instead of at a resumable window boundary.
    """

    state = {"cancelled": False}
    return (lambda: state["cancelled"]), (lambda _note: state.update(cancelled=True))


def _run_rehearsal(target, organization, actor, *, ordinal=1, rows=None, **overrides):
    values = {
        "settings_object": SimpleNamespace(),
        "policy": _policy(batch_rows=2),
        "organization": organization,
        "actor": actor,
        "report_dir": target.report_dir,
        "rehearsal_ordinal": ordinal,
        "apply_confirmation": "ignored-by-the-patched-confirmation",
        "source_path": _SOURCE_PATH,
        "source_size_bytes": _SOURCE_SIZE_BYTES,
        "source_preflight": _preflight,
        "source_factory_builder": lambda _settings: _factory(rows if rows is not None else _source_rows()),
    }
    values.update(overrides)
    return execute_rehearsal(**values)


# ---------------------------------------------------------------------------
# 34 / 35 — plan mode and the apply confirmation
# ---------------------------------------------------------------------------


def test_plan_mode_creates_no_run_and_writes_no_report(rehearsal_target, tmp_path):
    organization, actor = _organization("plan")

    payload = plan_rehearsal(
        settings_object=SimpleNamespace(),
        policy=_policy(),
        organization=organization,
        actor=actor,
        source_path=_SOURCE_PATH,
        source_size_bytes=_SOURCE_SIZE_BYTES,
        source_preflight=_preflight,
        source_factory_builder=lambda _settings: _factory(_source_rows()),
    )

    assert payload["status"] == "planned"
    assert payload["source_row_count"] == _STUDENT_ROWS + _WORKER_ROWS
    assert payload["snapshot_sha256"] == SOURCE_SNAPSHOT_SHA256
    assert payload["target_guard"]["database_name_shape"] == "emsarena_rehearsal_<12hex>"
    assert len(payload["attestation_digest"]) == 64
    assert LegacyMigrationRun.objects.count() == 0
    assert LegacyEntityObservation.objects.count() == 0
    assert list((tmp_path / "reports").iterdir()) == []
    # The plan payload must stay serializable and PII-free.
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    for forbidden in (_SOURCE_PATH, "student-1@example.test", "myedu.student.1", actor.username):
        assert forbidden not in serialized


def test_apply_requires_matching_apply_confirm(rehearsal_target, monkeypatch):
    organization, actor = _organization("confirm")
    monkeypatch.undo()  # restore the real confirmation gate, then re-patch the rest
    plan = rehearsal_target.plan
    monkeypatch.setattr(phase_a_module, "load_legacy_table_plan", lambda: plan)
    monkeypatch.setattr(phase_a_module, "assert_disposable_rehearsal_target", lambda **_kwargs: _GUARD)

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        execute_rehearsal(
            settings_object=SimpleNamespace(),
            policy=_policy(),
            organization=organization,
            actor=actor,
            report_dir=rehearsal_target.report_dir,
            rehearsal_ordinal=1,
            apply_confirmation="not-the-target-database-name",
            source_path=_SOURCE_PATH,
            source_size_bytes=_SOURCE_SIZE_BYTES,
            source_preflight=_preflight,
            source_factory_builder=lambda _settings: _factory(_source_rows()),
        )

    assert exc_info.value.code == "legacy_rehearsal_apply_confirmation_invalid"
    assert LegacyMigrationRun.objects.count() == 0


# ---------------------------------------------------------------------------
# 36 / 40 / 41 — full run, D5 and blocking issues
# ---------------------------------------------------------------------------


def test_full_run_reaches_succeeded_with_deny_all_policy(rehearsal_target):
    organization, actor = _organization("succeed")

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)
    assert outcome.status == LegacyMigrationRun.Status.SUCCEEDED
    assert outcome.failure_code == ""
    assert run.migrated_count == 0
    assert run.skipped_count == _STUDENT_ROWS + _WORKER_ROWS
    assert run.quarantined_count == 0
    assert LegacyEntityObservation.objects.filter(run=run).count() == _STUDENT_ROWS + _WORKER_ROWS
    assert LegacyImportBatch.objects.filter(run=run).count() == 3
    assert LegacyMigrationIssue.objects.filter(run=run, rule_code="legacy_rehearsal_attestation").count() == 1

    document = json.loads(open(outcome.report_path, encoding="ascii").read())
    assert document["determinism_digest"] == outcome.determinism_digest
    assert document["deterministic"]["totals"]["source_rows"] == _STUDENT_ROWS + _WORKER_ROWS
    assert document["deterministic"]["totals"]["staged_accounts"] == 0
    assert document["provenance"]["run_id"] == str(run.pk)
    assert outcome.report_path.endswith(REPORT_NAME_TEMPLATE.format(ordinal=1))
    for forbidden in ("myedu.student.1", "student-1@example.test", _SOURCE_PATH, actor.username):
        assert forbidden not in json.dumps(document, sort_keys=True)


def test_second_run_in_same_database_is_refused(rehearsal_target):
    organization, actor = _organization("d5")
    _run_rehearsal(rehearsal_target, organization, actor)

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _run_rehearsal(rehearsal_target, organization, actor, ordinal=2)

    assert exc_info.value.code == "legacy_rehearsal_scope_already_completed"
    assert LegacyMigrationRun.objects.filter(organization=organization).count() == 1


def test_error_severity_issue_forces_failed_outcome(rehearsal_target, monkeypatch):
    organization, actor = _organization("blocking")

    def unavailable_policy(_policy, _digests):
        def raise_policy(_identity):
            raise RuntimeError("policy-backend-unavailable")

        return raise_policy

    monkeypatch.setattr(orchestrator, "build_email_trust_policy", unavailable_policy)

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)
    assert outcome.status == LegacyMigrationRun.Status.FAILED
    assert outcome.failure_code == orchestrator.BLOCKING_ISSUE_FAILURE_CODE
    assert run.quarantined_count == _STUDENT_ROWS + _WORKER_ROWS
    assert (
        LegacyMigrationIssue.objects.filter(
            run=run,
            rule_code="legacy_account_email_trust_policy_unavailable",
            severity=LegacyMigrationIssue.Severity.ERROR,
        ).count()
        == _STUDENT_ROWS + _WORKER_ROWS
    )
    assert outcome.determinism_digest


# ---------------------------------------------------------------------------
# 37 / 38 / 39 — interruption, resume and scope binding
# ---------------------------------------------------------------------------


def test_interrupted_run_leaves_status_running_and_resumes_to_identical_digest(rehearsal_target):
    reference_organization, reference_actor = _organization("reference")
    resumed_organization, resumed_actor = _organization("resumed")

    reference = _run_rehearsal(rehearsal_target, reference_organization, reference_actor, ordinal=1)

    cancellation, note = _cancel_after_first_batch()

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        _run_rehearsal(
            rehearsal_target,
            resumed_organization,
            resumed_actor,
            ordinal=2,
            cancellation_requested=cancellation,
            stdout_note=note,
        )

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    interrupted = LegacyMigrationRun.objects.get(organization=resumed_organization)
    assert interrupted.status == LegacyMigrationRun.Status.RUNNING
    assert LegacyImportBatch.objects.filter(run=interrupted).count() == 1

    resumed = _run_rehearsal(
        rehearsal_target,
        resumed_organization,
        resumed_actor,
        ordinal=2,
        resume_run_id=interrupted.pk,
    )

    assert resumed.run_id == interrupted.pk
    assert resumed.status == LegacyMigrationRun.Status.SUCCEEDED
    # Run and organization identities are deliberately outside the digest.
    assert resumed.determinism_digest == reference.determinism_digest
    assert LegacyImportBatch.objects.filter(run=interrupted).count() == 3


def test_resume_skips_already_observed_rows_and_does_not_restage(rehearsal_target):
    organization, actor = _organization("resume-idempotent")
    cancellation, note = _cancel_after_first_batch()

    with pytest.raises(LegacyRehearsalInterrupted):
        _run_rehearsal(rehearsal_target, organization, actor, cancellation_requested=cancellation, stdout_note=note)

    run = LegacyMigrationRun.objects.get(organization=organization)
    first_pass_observations = set(
        LegacyEntityObservation.objects.filter(run=run).values_list("entity_map__legacy_pk", "state")
    )
    users_before = get_user_model()._default_manager.count()

    outcome = _run_rehearsal(rehearsal_target, organization, actor, resume_run_id=run.pk)

    assert outcome.status == LegacyMigrationRun.Status.SUCCEEDED
    assert get_user_model()._default_manager.count() == users_before
    assert LegacyEntityObservation.objects.filter(run=run).count() == _STUDENT_ROWS + _WORKER_ROWS
    assert first_pass_observations <= set(
        LegacyEntityObservation.objects.filter(run=run).values_list("entity_map__legacy_pk", "state")
    )
    assert LegacyEntityMap.objects.filter(organization=organization).count() == _STUDENT_ROWS + _WORKER_ROWS


def test_resume_refuses_scope_mismatch(rehearsal_target):
    organization, actor = _organization("scope")
    other_organization, _other_actor = _organization("scope-other")
    cancellation, note = _cancel_after_first_batch()

    with pytest.raises(LegacyRehearsalInterrupted):
        _run_rehearsal(rehearsal_target, organization, actor, cancellation_requested=cancellation, stdout_note=note)

    run = LegacyMigrationRun.objects.get(organization=organization)

    with pytest.raises(LegacyRehearsalResumeError) as exc_info:
        _run_rehearsal(rehearsal_target, other_organization, actor, resume_run_id=run.pk)

    assert exc_info.value.code == "legacy_rehearsal_resume_scope_mismatch"

    # A different policy changes transform_version, which is part of the scope.
    with pytest.raises(LegacyRehearsalResumeError) as exc_info:
        _run_rehearsal(
            rehearsal_target,
            organization,
            actor,
            resume_run_id=run.pk,
            policy=_policy(batch_rows=1),
        )

    assert exc_info.value.code == "legacy_rehearsal_resume_scope_mismatch"
    assert LegacyMigrationRun.objects.get(pk=run.pk).status == LegacyMigrationRun.Status.RUNNING


def test_cancel_run_finishes_an_interrupted_run(rehearsal_target):
    organization, actor = _organization("cancel")
    cancellation, note = _cancel_after_first_batch()

    with pytest.raises(LegacyRehearsalInterrupted):
        _run_rehearsal(rehearsal_target, organization, actor, cancellation_requested=cancellation, stdout_note=note)

    run = LegacyMigrationRun.objects.get(organization=organization)
    outcome = cancel_rehearsal(
        settings_object=SimpleNamespace(),
        organization=organization,
        actor=actor,
        run_id=run.pk,
    )

    assert outcome.status == LegacyMigrationRun.Status.CANCELLED
    assert outcome.failure_code == "legacy_rehearsal_cancelled"
    assert outcome.report_path == ""


# ---------------------------------------------------------------------------
# 42 / 43 — determinism comparison and the RLS contract
# ---------------------------------------------------------------------------


def test_compare_report_mismatch_fails_closed(rehearsal_target, tmp_path):
    # All three organizations exist before the first run so the pre-run target
    # identity baseline — which IS part of the determinism digest — is stable.
    first_organization, first_actor = _organization("compare-one")
    second_organization, second_actor = _organization("compare-two")
    third_organization, third_actor = _organization("compare-three")

    first = _run_rehearsal(rehearsal_target, first_organization, first_actor, ordinal=1)
    matching = _run_rehearsal(
        rehearsal_target,
        second_organization,
        second_actor,
        ordinal=2,
        compare_report_path=first.report_path,
    )

    assert matching.status == LegacyMigrationRun.Status.SUCCEEDED
    assert matching.determinism_digest == first.determinism_digest

    divergent = tmp_path / "divergent.json"
    document = json.loads(open(first.report_path, encoding="ascii").read())
    document["deterministic"]["snapshot_size_bytes"] = _SOURCE_SIZE_BYTES + 1
    document["determinism_digest"] = orchestrator.canonical_json_digest(document["deterministic"])
    divergent.write_text(json.dumps(document, ensure_ascii=True, sort_keys=True) + "\n", encoding="ascii")
    third_report_dir = tmp_path / "third"
    third_report_dir.mkdir()

    mismatched = _run_rehearsal(
        rehearsal_target,
        third_organization,
        third_actor,
        ordinal=2,
        report_dir=str(third_report_dir),
        compare_report_path=str(divergent),
    )

    assert mismatched.determinism_digest == first.determinism_digest
    assert mismatched.status == LegacyMigrationRun.Status.FAILED
    assert mismatched.failure_code == "legacy_rehearsal_determinism_mismatch"
    assert LegacyMigrationRun.objects.get(pk=mismatched.run_id).failure_code == "legacy_rehearsal_determinism_mismatch"


def test_run_never_calls_bypass_rls(rehearsal_target, monkeypatch):
    organization, actor = _organization("rls")
    calls = {"bypass": 0, "tenant": []}

    import core.rls as rls_module

    def forbidden_bypass(*_args, **_kwargs):  # pragma: no cover - must never run
        calls["bypass"] += 1
        raise AssertionError("the rehearsal must never bypass RLS")

    monkeypatch.setattr(rls_module, "bypass_rls", forbidden_bypass)
    monkeypatch.setattr(rls_module, "set_rls_bypass", forbidden_bypass)
    monkeypatch.setattr(phase_a_module, "set_rls_tenant", lambda org_id, **kwargs: calls["tenant"].append(org_id))

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    assert outcome.status == LegacyMigrationRun.Status.SUCCEEDED
    assert calls["bypass"] == 0
    assert calls["tenant"] == [organization.pk]


def test_authoritative_email_decision_is_never_inferred(rehearsal_target):
    """A deny_all rehearsal must classify every row as untrusted, not eligible."""

    organization, actor = _organization("deny-all")

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)
    assert (
        LegacyMigrationIssue.objects.filter(run=run, rule_code="legacy_account_email_untrusted").count()
        == _STUDENT_ROWS + _WORKER_ROWS
    )
    assert EmailTrustDecision.AUTHORITATIVE not in set(
        LegacyEntityObservation.objects.filter(run=run).values_list("state", flat=True)
    )


def test_emit_report_only_regenerates_an_identical_digest(rehearsal_target):
    """The artifact must be reproducible from the sealed ledger alone."""

    organization, actor = _organization("emit-only")
    outcome = _run_rehearsal(rehearsal_target, organization, actor)
    original = open(outcome.report_path, encoding="ascii").read()

    regenerated = _run_rehearsal(
        rehearsal_target,
        organization,
        actor,
        resume_run_id=outcome.run_id,
        emit_report_only=True,
    )

    assert regenerated.determinism_digest == outcome.determinism_digest
    assert regenerated.status == LegacyMigrationRun.Status.SUCCEEDED
    assert json.loads(open(regenerated.report_path, encoding="ascii").read())["deterministic"] == (
        json.loads(original)["deterministic"]
    )
    # No second run row and no extra ledger material were created.
    assert LegacyMigrationRun.objects.filter(organization=organization).count() == 1
    assert LegacyImportBatch.objects.filter(run_id=outcome.run_id).count() == 3


def test_emit_report_only_requires_a_run_id(rehearsal_target):
    organization, actor = _organization("emit-only-missing")

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _run_rehearsal(rehearsal_target, organization, actor, emit_report_only=True)

    assert exc_info.value.code == "legacy_rehearsal_report_run_required"


# ---------------------------------------------------------------------------
# SA-1 / SA-2 — the derived (batch-less) phase seam
# ---------------------------------------------------------------------------

_DERIVED_PHASE_KEY = "stub_derived"
_DERIVED_ENTITY_TYPE = "stub_derived_row"
_STRAY_ENTITY_TYPE = "stub_stray_row"
_DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-stub-derived-v1"
_DERIVED_STATE_KEYS = {
    str(LegacyEntityMap.State.MIGRATED): "record_created",
    str(LegacyEntityMap.State.SKIPPED): "record_deferred",
    str(LegacyEntityMap.State.QUARANTINED): "record_unresolved",
}
_DERIVED_ROWS = (
    (1, LegacyEntityMap.State.SKIPPED),
    (2, LegacyEntityMap.State.SKIPPED),
    (3, LegacyEntityMap.State.QUARANTINED),
)


def _derivation_hash(legacy_pk) -> str:
    """Stand in for the placement phase's cross-run-stable derivation hash."""

    return hashlib.sha256(f"stub-derivation-v1\x00{legacy_pk}".encode()).hexdigest()


class _StubDerivedPhase:
    """A phase that accounts for no source table and owns no batch chain.

    It is the smallest possible stand-in for ``student_placement``: it writes
    one ledger observation per derived decision, chains them itself, and reports
    ``observed_source_rows = 0`` with token state keys.
    """

    phase_key = _DERIVED_PHASE_KEY
    order = 25
    source_tables = ()
    entity_types = (_DERIVED_ENTITY_TYPE,)
    derived_digest_namespace = _DERIVED_DIGEST_NAMESPACE

    def __init__(self, *, rows=_DERIVED_ROWS, written_entity_type=_DERIVED_ENTITY_TYPE):
        self.rows = tuple(rows)
        self.written_entity_type = written_entity_type
        self.last_report = None

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:
        return _DERIVED_STATE_KEYS[str(state)]

    def run(self, context):
        chain = OrderedDigest(_DERIVED_DIGEST_NAMESPACE)
        counts = Counter()
        for legacy_pk, state in self.rows:
            row_hash = _derivation_hash(legacy_pk)
            upsert_entity_map(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                entity_type=self.written_entity_type,
                legacy_pk=str(legacy_pk),
                source_row_hash=row_hash,
                state=state,
                target_model_label="",
                target_pk="",
                target_validators=context.target_validators,
            )
            chain.advance(str(legacy_pk), str(state), row_hash, "")
            counts[self.derived_state_key(state)] += 1
        self.last_report = PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(counts),
            issue_counts={},
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )
        return self.last_report


def _register_derived_phase(monkeypatch, stub):
    """Drive the real orchestrator over ``(identity_cohort, <stub>)``."""

    registry = (IdentityCohortPhase(), stub)
    monkeypatch.setattr(phase_a_module, "load_rehearsal_phase_registry", lambda: registry)
    return _policy(batch_rows=2, phase_keys=("identity_cohort", _DERIVED_PHASE_KEY))


def test_sa1_derived_observations_do_not_break_the_batch_cross_check(rehearsal_target, monkeypatch):
    """SA-1: C4 counts only the observations the batch chain accounts for."""

    organization, actor = _organization("derived-c4")
    stub = _StubDerivedPhase()
    policy = _register_derived_phase(monkeypatch, stub)

    outcome = _run_rehearsal(rehearsal_target, organization, actor, policy=policy)

    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)
    assert outcome.status == LegacyMigrationRun.Status.SUCCEEDED
    # The batch chain still accounts for the identity rows and nothing else...
    assert run.skipped_count == _STUDENT_ROWS + _WORKER_ROWS
    assert run.quarantined_count == 0
    assert LegacyImportBatch.objects.filter(run=run).count() == 3
    # ...while the derived rows exist in the ledger beside them.
    assert LegacyEntityObservation.objects.filter(run=run).count() == _STUDENT_ROWS + _WORKER_ROWS + len(_DERIVED_ROWS)
    assert LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type=_DERIVED_ENTITY_TYPE).count() == len(
        _DERIVED_ROWS
    )
    # Re-running C4 against the sealed run is still clean.
    reconcile_run(run, phases=(IdentityCohortPhase(), stub), plan=rehearsal_target.plan)

    document = json.loads(open(outcome.report_path, encoding="ascii").read())
    derived_entry = next(entry for entry in document["deterministic"]["phases"] if entry["phase_key"] == "stub_derived")
    assert derived_entry["source_tables"] == [] and derived_entry["batches"] == []
    assert derived_entry["state_counts"] == {"record_deferred": 2, "record_unresolved": 1}
    # Token state keys stay out of the operator-facing rehearsal totals.
    totals = document["deterministic"]["totals"]
    assert totals["skipped"] == _STUDENT_ROWS + _WORKER_ROWS
    assert totals["quarantined"] == 0
    assert totals["source_rows"] == _STUDENT_ROWS + _WORKER_ROWS


def test_sa1_observation_under_an_undeclared_entity_type_fails_closed(rehearsal_target, monkeypatch):
    """SA-1 fail-closed half: relaxing C4 must not open an unaccounted lane."""

    organization, actor = _organization("derived-stray")
    stub = _StubDerivedPhase(written_entity_type=_STRAY_ENTITY_TYPE)
    policy = _register_derived_phase(monkeypatch, stub)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        _run_rehearsal(rehearsal_target, organization, actor, policy=policy)

    assert exc_info.value.code == "legacy_rehearsal_derived_entity_type_unregistered"
    run = LegacyMigrationRun.objects.get(organization=organization)
    assert run.status == LegacyMigrationRun.Status.FAILED
    assert run.failure_code == "legacy_rehearsal_derived_entity_type_unregistered"


def test_sa2_phase_report_from_ledger_rebuilds_a_batch_less_phase(rehearsal_target, monkeypatch):
    """SA-2: the derived report is reproducible from the observations alone."""

    organization, actor = _organization("derived-rebuild")
    stub = _StubDerivedPhase()
    policy = _register_derived_phase(monkeypatch, stub)

    outcome = _run_rehearsal(rehearsal_target, organization, actor, policy=policy)
    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)

    rebuilt = phase_report_from_ledger(run, phase=stub, plan=rehearsal_target.plan)

    assert rebuilt == stub.last_report
    assert rebuilt.phase_digest == stub.last_report.phase_digest
    assert rebuilt.state_counts == {"record_deferred": 2, "record_unresolved": 1}
    assert rebuilt.source_tables == () and rebuilt.batches == ()
    assert rebuilt.observed_source_rows == 0 and rebuilt.staged_account_count == 0


def test_sa2_emit_report_only_reproduces_a_run_containing_a_derived_phase(rehearsal_target, monkeypatch):
    """The whole artifact — not just the phase entry — regenerates identically."""

    organization, actor = _organization("derived-emit")
    stub = _StubDerivedPhase()
    policy = _register_derived_phase(monkeypatch, stub)

    outcome = _run_rehearsal(rehearsal_target, organization, actor, policy=policy)
    original = json.loads(open(outcome.report_path, encoding="ascii").read())

    regenerated = _run_rehearsal(
        rehearsal_target,
        organization,
        actor,
        policy=policy,
        resume_run_id=outcome.run_id,
        emit_report_only=True,
    )

    assert regenerated.determinism_digest == outcome.determinism_digest
    assert json.loads(open(regenerated.report_path, encoding="ascii").read())["deterministic"] == (
        original["deterministic"]
    )


def test_sa2_derived_rebuild_defaults_when_the_optional_hooks_are_absent(rehearsal_target, monkeypatch):
    """Both SA-2 hooks are optional; without them the shared defaults apply."""

    organization, actor = _organization("derived-defaults")
    stub = _StubDerivedPhase()
    policy = _register_derived_phase(monkeypatch, stub)
    outcome = _run_rehearsal(rehearsal_target, organization, actor, policy=policy)
    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)

    plain = SimpleNamespace(
        phase_key=_DERIVED_PHASE_KEY,
        order=25,
        source_tables=(),
        entity_types=(_DERIVED_ENTITY_TYPE,),
        declared_source_rows=lambda _plan: 0,
    )

    rebuilt = phase_report_from_ledger(run, phase=plain, plan=rehearsal_target.plan)

    # Raw ledger states, not the phase's own tokens...
    assert rebuilt.state_counts == {"skipped": 2, "quarantined": 1}
    # ...and the shared phase namespace, so the digest deliberately differs.
    assert rebuilt.phase_digest != stub.last_report.phase_digest


def test_sa2_derived_rebuild_refuses_a_non_numeric_legacy_pk(rehearsal_target, monkeypatch):
    """Ordering the rebuild numerically must fail closed, never fall back."""

    organization, actor = _organization("derived-badpk")
    stub = _StubDerivedPhase(rows=(("alpha", LegacyEntityMap.State.SKIPPED),))
    policy = _register_derived_phase(monkeypatch, stub)

    outcome = _run_rehearsal(rehearsal_target, organization, actor, policy=policy)
    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_report_from_ledger(run, phase=stub, plan=rehearsal_target.plan)

    assert exc_info.value.code == "legacy_rehearsal_derived_legacy_pk_invalid"
