"""Phase B (identity cohort) tests: streaming, digests, staging and rebase."""

from dataclasses import replace
from types import MappingProxyType, SimpleNamespace

from django.contrib.auth.validators import UnicodeUsernameValidator

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services import account_cutover
from apps.legacy_import.services import rehearsal_identity_phase as phase_module
from apps.legacy_import.services.account_cutover import (
    EmailTrustDecision,
    ProjectedAccountIdentity,
    TargetIdentitySnapshot,
    classify_projected_account_cutover,
    deny_all_email_trust,
    load_target_identity_snapshot,
)
from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    compile_safe_projection,
)
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map
from apps.legacy_import.services.pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from apps.legacy_import.services.rehearsal_authorizer import USER_MODEL_LABEL, build_target_validators
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from apps.legacy_import.services.rehearsal_identity_phase import (
    ISSUE_SEVERITY,
    IdentityCohortPhase,
    build_email_trust_policy,
    email_evidence_digest,
    load_email_trust_manifest,
    rebase_target_snapshot_for_run,
)
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable, LegacySourceExtractionCancelled
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import Organization
from core.constants import OrganizationType

_SNAPSHOT_SHA256 = load_legacy_table_plan().source_snapshot_sha256
_CONTRACTS = {
    "students": STUDENT_IDENTITY_FIELDS,
    "workers": WORKER_IDENTITY_FIELDS,
}
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "show_password", "pin_for_lock")
_EMPTY_SNAPSHOT = TargetIdentitySnapshot(
    usernames=MappingProxyType({}),
    emails=MappingProxyType({}),
    row_count=0,
)


class _FakeCursor:
    """Positional DB-API cursor over already-projected source values."""

    def __init__(self, description, rows):
        self.description = description
        self._rows = list(rows)
        self._position = 0
        self.close_calls = 0

    def fetchmany(self, size):
        chunk = self._rows[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def close(self):
        self.close_calls += 1


class _FakeSourceConnection:
    """Read-only source that only ever returns contract-projected columns."""

    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.statements = []
        self.cursors = []
        self.rolled_back = False
        self.closed = False

    def server_is_read_only(self):
        return True

    def begin_read_only_snapshot(self):
        return None

    def session_is_read_only(self):
        return True

    def discover_table(self, source_table):
        contract = _CONTRACTS[source_table]
        return LegacyDiscoveredTable(
            source_table=source_table,
            column_names=(*contract.allowed_fields, *_CREDENTIAL_COLUMNS),
            primary_key_fields=("id",),
        )

    def open_compiled_select(self, query):
        self.statements.append(query.mysql_statement())
        field_names = query.projection.field_names
        rows = self.rows_by_table.get(query.projection.source_table, ())
        cursor = _FakeCursor(
            tuple((field_name, None, None, None, None, None, None) for field_name in field_names),
            [tuple(row[field_name] for field_name in field_names) for row in rows],
        )
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _factory(rows_by_table):
    connections = []

    def build():
        connection = _FakeSourceConnection(rows_by_table)
        connections.append(connection)
        return connection

    build.connections = connections
    return build


def _row(contract, legacy_pk, *, email=None, **overrides):
    values = {field_name: None for field_name in contract.allowed_fields}
    values["id"] = legacy_pk
    values["email"] = email
    values["password"] = "hunter2-raw-credential"
    values.update(overrides)
    return values


def _plan(*, students=0, workers=0):
    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=students + workers,
        entries=(
            replace(canonical.entry_for("students"), expected_rows=students),
            replace(canonical.entry_for("workers"), expected_rows=workers),
        ),
    )


def _policy(**overrides):
    values = {
        "phase_keys": ("identity_cohort",),
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.DENY_ALL,
        "email_trust_manifest_digest": "",
        "batch_rows": DEFAULT_BATCH_ROWS,
        "source_chunk_size": 1_000,
        "max_staged_accounts": 0,
        "student_role_name": "",
        "worker_role_name": "",
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _allow(**_kwargs):
    return True


def _authoritative(_identity):
    return EmailTrustDecision.AUTHORITATIVE


def _context(
    *,
    plan,
    factory,
    policy=None,
    run_id=None,
    organization=None,
    actor=None,
    snapshot=_EMPTY_SNAPSHOT,
    email_policy=deny_all_email_trust,
    target_validators=None,
    cancelled=False,
    cancellation=None,
    notes=None,
):
    return RehearsalContext(
        run_id=run_id,
        organization=organization,
        actor=actor,
        authorize=_allow,
        target_validators=target_validators if target_validators is not None else {},
        policy=policy or _policy(),
        plan=plan,
        source_connection_factory=factory,
        target_identity_snapshot=snapshot,
        authoritative_email_policy=email_policy,
        cancellation_requested=cancellation if cancellation is not None else (lambda: cancelled),
        stdout_note=(notes if notes is not None else []).append,
    )


def _staged_user(target_pk):
    from django.contrib.auth import get_user_model

    return get_user_model()._default_manager.get(pk=target_pk)


def _identity(contract, legacy_pk, *, email, username):
    projection = compile_safe_projection(contract, discovered_fields=contract.allowed_fields)
    values = {field_name: None for field_name in contract.allowed_fields}
    values["id"] = legacy_pk
    values["email"] = email
    return ProjectedAccountIdentity(
        projected_row=projection.accept_extracted_row(values),
        proposed_username=username,
    )


# ---------------------------------------------------------------------------
# Cohort streaming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("legacy_pk", ["7421", 7421.0, True, None])
def test_cohort_stream_rejects_non_integer_pk(legacy_pk):
    context = _context(
        plan=_plan(students=1),
        factory=_factory({"students": [_row(STUDENT_IDENTITY_FIELDS, legacy_pk)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_module._build_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_type_drift"


@pytest.mark.parametrize("legacy_pk", [0, -1, MAX_LEDGER_PRIMARY_KEY + 1])
def test_cohort_stream_rejects_out_of_range_pk(legacy_pk):
    context = _context(
        plan=_plan(students=1),
        factory=_factory({"students": [_row(STUDENT_IDENTITY_FIELDS, legacy_pk)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_module._build_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_out_of_range"


@pytest.mark.parametrize("second_pk", [1, 7])
def test_cohort_stream_rejects_descending_pk(second_pk):
    context = _context(
        plan=_plan(students=2),
        factory=_factory(
            {
                "students": [
                    _row(STUDENT_IDENTITY_FIELDS, 7),
                    _row(STUDENT_IDENTITY_FIELDS, second_pk),
                ]
            }
        ),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_module._build_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_order_invalid"


@pytest.mark.parametrize("observed_rows", [1, 3])
def test_cohort_row_count_must_equal_plan_expected_rows(observed_rows):
    context = _context(
        plan=_plan(students=2),
        factory=_factory({"students": [_row(STUDENT_IDENTITY_FIELDS, index) for index in range(1, observed_rows + 1)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_module._build_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_row_count_mismatch"


def test_cohort_refuses_a_table_larger_than_the_bounded_cap():
    context = _context(plan=_plan(students=20_001), factory=_factory({"students": []}))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        phase_module._build_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_cohort_too_large"


def test_credential_columns_never_reach_the_cohort():
    factory = _factory(
        {
            "students": [_row(STUDENT_IDENTITY_FIELDS, 7421, email="student@example.test")],
            "workers": [_row(WORKER_IDENTITY_FIELDS, 12, email="worker@example.test")],
        }
    )
    context = _context(plan=_plan(students=1, workers=1), factory=factory)

    rows = phase_module._build_cohort(context)

    assert [row.legacy_pk for row in rows] == [7421, 12]
    assert [row.entity_type for row in rows] == ["student", "worker"]
    assert tuple(rows[0].identity.projected_row) == STUDENT_IDENTITY_FIELDS.allowed_fields
    for row in rows:
        for credential_field in _CREDENTIAL_COLUMNS:
            with pytest.raises(KeyError):
                row.identity.projected_row[credential_field]
        assert "hunter2-raw-credential" not in repr(row.identity.projected_row)
        assert "hunter2-raw-credential" not in repr(row.identity)
        assert len(row.source_row_hash) == 64
    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 2
    assert all("password" not in statement for statement in statements)
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


def test_proposed_username_is_deterministic_and_validator_clean():
    policy = _policy()
    validate_username = UnicodeUsernameValidator()

    assert phase_module._proposed_username(policy, "student", 7421) == "myedu.student.7421"
    assert phase_module._proposed_username(policy, "worker", 12) == "myedu.worker.12"
    assert phase_module._proposed_username(policy, "student", 7421) == phase_module._proposed_username(
        policy, "student", 7421
    )
    validate_username("myedu.student.7421")
    validate_username("myedu.worker.12")
    assert phase_module._student_identifier(policy, "student", 7421) == "myedu-student-7421"
    assert phase_module._student_identifier(policy, "worker", 7421) == ""

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        phase_module._proposed_username(SimpleNamespace(username_policy="legacy_key"), "student", 1)

    assert exc_info.value.code == "legacy_rehearsal_username_policy_unsupported"


def test_batch_windows_are_deterministic_for_a_given_batch_rows():
    rows = phase_module._build_cohort(
        _context(
            plan=_plan(students=5),
            factory=_factory({"students": [_row(STUDENT_IDENTITY_FIELDS, index) for index in range(1, 6)]}),
        )
    )

    first_pass = [[row.legacy_pk for row in window] for window in phase_module._chunked(rows, 2)]
    second_pass = [[row.legacy_pk for row in window] for window in phase_module._chunked(rows, 2)]
    wider = [[row.legacy_pk for row in window] for window in phase_module._chunked(rows, 4)]

    assert first_pass == second_pass == [[1, 2], [3, 4], [5]]
    assert wider == [[1, 2, 3, 4], [5]]
    assert [[row.legacy_pk for row in window] for window in phase_module._chunked(rows, 500)] == [[1, 2, 3, 4, 5]]


def test_students_and_workers_are_classified_as_one_cohort():
    shared_email = "shared@example.test"
    rows = phase_module._build_cohort(
        _context(
            plan=_plan(students=1, workers=1),
            factory=_factory(
                {
                    "students": [_row(STUDENT_IDENTITY_FIELDS, 1, email=shared_email)],
                    "workers": [_row(WORKER_IDENTITY_FIELDS, 1, email=shared_email)],
                }
            ),
        )
    )

    together = classify_projected_account_cutover(
        [row.identity for row in rows],
        authoritative_email_policy=_authoritative,
        target_identity_snapshot=_EMPTY_SNAPSHOT,
    )
    apart = [
        classify_projected_account_cutover(
            [row.identity],
            authoritative_email_policy=_authoritative,
            target_identity_snapshot=_EMPTY_SNAPSHOT,
        )[0]
        for row in rows
    ]

    assert [item.source_kind for item in together] == ["student", "worker"]
    assert all("legacy_account_email_duplicate_source" in item.rule_codes for item in together)
    # Split cohorts would silently miss the cross-table duplicate.
    assert all(item.rule_codes == () for item in apart)


# ---------------------------------------------------------------------------
# Email-authority evidence
# ---------------------------------------------------------------------------


def test_email_trust_manifest_is_digest_only_and_fails_closed(tmp_path):
    trusted = email_evidence_digest("Trusted@Example.Test")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text(f"# reviewed 2026-08-25\n{trusted}\n\n", encoding="ascii")

    digests, manifest_digest = load_email_trust_manifest(str(manifest))

    assert digests == frozenset({trusted})
    assert len(manifest_digest) == 64
    assert email_evidence_digest(" trusted@example.test ") == trusted

    broken = tmp_path / "broken.txt"
    broken.write_text("not-a-digest\n", encoding="ascii")
    for path, code in (
        (str(broken), "legacy_rehearsal_email_manifest_invalid"),
        (str(tmp_path / "missing.txt"), "legacy_rehearsal_email_manifest_unreadable"),
        ("", "legacy_rehearsal_email_manifest_invalid"),
    ):
        with pytest.raises(LegacyRehearsalConfigError) as exc_info:
            load_email_trust_manifest(path)
        assert exc_info.value.code == code


def test_email_trust_policy_grants_authority_only_to_manifest_digests():
    trusted_identity = _identity(STUDENT_IDENTITY_FIELDS, 1, email="Trusted@Example.Test", username="myedu.student.1")
    other_identity = _identity(STUDENT_IDENTITY_FIELDS, 2, email="other@example.test", username="myedu.student.2")
    blank_identity = _identity(STUDENT_IDENTITY_FIELDS, 3, email=None, username="myedu.student.3")
    manifest = frozenset({email_evidence_digest("trusted@example.test")})
    policy = build_email_trust_policy(
        _policy(email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST, email_trust_manifest_digest="a" * 64),
        manifest,
    )

    assert policy(trusted_identity) is EmailTrustDecision.AUTHORITATIVE
    assert policy(other_identity) is EmailTrustDecision.DENIED
    assert policy(blank_identity) is EmailTrustDecision.DENIED
    assert policy("not-an-identity") is EmailTrustDecision.DENIED
    assert build_email_trust_policy(_policy(), frozenset()) is deny_all_email_trust

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        build_email_trust_policy(_policy(), manifest)
    assert exc_info.value.code == "legacy_rehearsal_policy_email_trust_invalid"

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        build_email_trust_policy(
            _policy(email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST, email_trust_manifest_digest="a" * 64),
            frozenset(),
        )
    assert exc_info.value.code == "legacy_rehearsal_policy_email_trust_invalid"


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_issue_severity_map_covers_every_account_cutover_rule():
    expected = {
        "legacy_account_email_untrusted": "info",
        "legacy_account_email_blank": "info",
        "legacy_account_email_invalid": "warning",
        "legacy_account_username_blank": "warning",
        "legacy_account_username_invalid": "warning",
        "legacy_account_username_collision": "warning",
        "legacy_account_email_collision": "warning",
        "legacy_account_email_duplicate_existing": "warning",
        "legacy_account_email_duplicate_source": "warning",
        "legacy_account_username_duplicate_source": "warning",
        "legacy_account_username_email_collision": "warning",
        "legacy_account_username_email_duplicate_source": "warning",
        "legacy_account_identity_probe_unavailable": "error",
        "legacy_account_email_trust_policy_unavailable": "error",
        "legacy_rehearsal_stage_cap_reached": "warning",
        "legacy_rehearsal_staging_refused": "error",
        "legacy_rehearsal_attestation": "info",
    }

    assert dict(ISSUE_SEVERITY) == expected
    assert set(account_cutover._MANUAL_REVIEW_RULES) <= set(ISSUE_SEVERITY)
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)

    def unavailable(_identity):
        raise RuntimeError("raw-policy-failure")

    snapshot = TargetIdentitySnapshot(
        usernames=MappingProxyType({"myedu.student.9": 1}),
        emails=MappingProxyType({"existing@example.test": 2}),
        row_count=3,
    )
    cohort = (
        _identity(STUDENT_IDENTITY_FIELDS, 1, email="dupe@example.test", username="myedu.student.1"),
        _identity(WORKER_IDENTITY_FIELDS, 1, email="dupe@example.test", username="myedu.student.1"),
        _identity(STUDENT_IDENTITY_FIELDS, 3, email=None, username="myedu.student.3"),
        _identity(STUDENT_IDENTITY_FIELDS, 4, email="not-an-email", username="myedu.student.4"),
        _identity(STUDENT_IDENTITY_FIELDS, 5, email="existing@example.test", username=""),
        _identity(STUDENT_IDENTITY_FIELDS, 6, email="six@example.test", username="not a username"),
        _identity(STUDENT_IDENTITY_FIELDS, 9, email="nine@example.test", username="myedu.student.9"),
    )
    produced = {
        rule_code
        for classification in classify_projected_account_cutover(
            cohort,
            authoritative_email_policy=unavailable,
            target_identity_snapshot=snapshot,
        )
        for rule_code in classification.rule_codes
    }

    assert len(produced) >= 8
    assert produced <= set(ISSUE_SEVERITY)
    for rule_code in produced:
        assert phase_module._severity_for(rule_code) in set(LegacyMigrationIssue.Severity.values)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        phase_module._severity_for("legacy_rehearsal_rule_that_is_not_mapped")
    assert exc_info.value.code == "legacy_rehearsal_issue_severity_unmapped"


# ---------------------------------------------------------------------------
# Ledger-backed behaviour
# ---------------------------------------------------------------------------


@pytest.fixture()
def rehearsal_environment(db, django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="rehearsal_phase_actor",
        email="rehearsal-phase-actor@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Rehearsal Phase Organization",
        slug="rehearsal-phase-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    return organization, actor


def _running_run(organization, actor, *, policy, plan, source_row_count):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=_SNAPSHOT_SHA256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=source_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{plan.fingerprint[:12]}",
        transform_version=policy.transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


@pytest.mark.django_db
def test_phase_run_seals_batches_and_replays_identically(rehearsal_environment):
    organization, actor = rehearsal_environment
    policy = _policy(batch_rows=2)
    plan = _plan(students=3, workers=2)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=5)
    notes = []
    context = _context(
        plan=plan,
        factory=_factory(
            {
                "students": [
                    _row(STUDENT_IDENTITY_FIELDS, index, email=f"student-{index}@example.test") for index in range(1, 4)
                ],
                "workers": [
                    _row(WORKER_IDENTITY_FIELDS, index, email=f"worker-{index}@example.test") for index in range(1, 3)
                ],
            }
        ),
        policy=policy,
        run_id=run.pk,
        organization=organization,
        actor=actor,
        target_validators=build_target_validators(),
        notes=notes,
    )

    report = IdentityCohortPhase().run(context)

    assert report.phase_key == "identity_cohort"
    assert report.order == 20
    assert report.observed_source_rows == 5 == report.declared_source_rows
    assert report.staged_account_count == 0
    assert dict(report.state_counts) == {"migrated": 0, "skipped": 5, "quarantined": 0}
    assert dict(report.issue_counts) == {("legacy_account_email_untrusted", "info"): 5}
    assert [(record.source_table, record.sequence) for record in report.batches] == [
        ("students", 1),
        ("students", 2),
        ("workers", 1),
    ]
    assert [(record.first_legacy_pk, record.last_legacy_pk) for record in report.batches] == [(1, 2), (3, 3), (1, 2)]
    assert LegacyImportBatch.objects.filter(run=run).count() == 3
    assert LegacyEntityObservation.objects.filter(run=run, state=LegacyEntityMap.State.SKIPPED).count() == 5
    assert LegacyMigrationIssue.objects.filter(run=run, severity="info").count() == 5
    assert notes == [
        "identity_cohort.students.batch.1",
        "identity_cohort.students.batch.2",
        "identity_cohort.workers.batch.1",
    ]

    replay = IdentityCohortPhase().run(context)

    assert replay == report
    assert LegacyImportBatch.objects.filter(run=run).count() == 3
    assert LegacyEntityObservation.objects.filter(run=run).count() == 5
    assert LegacyMigrationIssue.objects.filter(run=run).count() == 5


@pytest.mark.django_db
def test_phase_run_stops_on_a_cancellation_request(rehearsal_environment):
    organization, actor = rehearsal_environment
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)
    requested = {"cancelled": False}

    def deny_and_request_cancellation(_identity):
        # Classification runs after the cohort is streamed and before the first
        # window, so this arms the phase-level (not source-level) interlock.
        requested["cancelled"] = True
        return EmailTrustDecision.DENIED

    def _phase_context(**overrides):
        values = {
            "plan": plan,
            "factory": _factory({"students": [_row(STUDENT_IDENTITY_FIELDS, 1, email="student-1@example.test")]}),
            "policy": policy,
            "run_id": run.pk,
            "organization": organization,
            "actor": actor,
            "target_validators": build_target_validators(),
        }
        values.update(overrides)
        return _context(**values)

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        IdentityCohortPhase().run(
            _phase_context(
                email_policy=deny_and_request_cancellation,
                cancellation=lambda: requested["cancelled"],
            )
        )

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    assert LegacyEntityObservation.objects.filter(run=run).count() == 0

    # A cancellation raised before the first row closes the source transport
    # instead, which is the extractor's own contract.
    with pytest.raises(LegacySourceExtractionCancelled):
        IdentityCohortPhase().run(_phase_context(cancelled=True))

    assert LegacyImportBatch.objects.filter(run=run).count() == 0


@pytest.mark.django_db
def test_snapshot_rebase_restores_pre_run_baseline(rehearsal_environment):
    organization, actor = rehearsal_environment
    manifest = frozenset(
        {
            email_evidence_digest("student-1@example.test"),
            email_evidence_digest("worker-1@example.test"),
        }
    )
    policy = _policy(
        email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST,
        email_trust_manifest_digest="b" * 64,
        max_staged_accounts=2,
        student_role_name="student",
        worker_role_name="teacher",
    )
    plan = _plan(students=1, workers=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=2)
    baseline = load_target_identity_snapshot()
    context = _context(
        plan=plan,
        factory=_factory(
            {
                "students": [_row(STUDENT_IDENTITY_FIELDS, 1, email="student-1@example.test")],
                "workers": [_row(WORKER_IDENTITY_FIELDS, 1, email="worker-1@example.test")],
            }
        ),
        policy=policy,
        run_id=run.pk,
        organization=organization,
        actor=actor,
        snapshot=baseline,
        email_policy=build_email_trust_policy(policy, manifest),
        target_validators=build_target_validators(),
    )

    report = IdentityCohortPhase().run(context)

    assert report.staged_account_count == 2
    assert dict(report.state_counts) == {"migrated": 2, "skipped": 0, "quarantined": 0}
    staged_user = LegacyEntityObservation.objects.get(run=run, entity_map__entity_type="student").target_pk
    staged = _staged_user(staged_user)
    assert staged.username == "myedu.student.1"
    assert staged.is_active is False
    assert staged.has_usable_password() is False
    assert staged.profile.access_state == UserProfile.AccessState.STAGED
    assert staged.profile.institutional_identifier == "myedu-student-1"
    assert staged.memberships.get(organization=organization).is_active is False

    after_staging = load_target_identity_snapshot()
    rebased = rebase_target_snapshot_for_run(after_staging, run_id=run.pk)

    assert after_staging.row_count == baseline.row_count + 2
    assert rebased.row_count == baseline.row_count
    assert dict(rebased.usernames) == dict(baseline.usernames)
    assert dict(rebased.emails) == dict(baseline.emails)


@pytest.mark.django_db
def test_snapshot_rebase_is_a_noop_without_staged_rows(rehearsal_environment):
    organization, actor = rehearsal_environment
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)
    baseline = load_target_identity_snapshot()

    assert rebase_target_snapshot_for_run(baseline, run_id=run.pk) is baseline

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        rebase_target_snapshot_for_run("not-a-snapshot", run_id=run.pk)
    assert exc_info.value.code == "legacy_rehearsal_resume_snapshot_invalid"


@pytest.mark.django_db
def test_snapshot_rebase_fails_closed_when_staged_user_is_missing(rehearsal_environment):
    organization, actor = rehearsal_environment
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)
    upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk="7421",
        source_row_hash="c" * 64,
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label=USER_MODEL_LABEL,
        target_pk="99999999",
        target_validators={USER_MODEL_LABEL: lambda **_kwargs: TargetValidation(True, True)},
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        rebase_target_snapshot_for_run(load_target_identity_snapshot(), run_id=run.pk)

    assert exc_info.value.code == "legacy_rehearsal_resume_target_missing"
