"""PostgreSQL-only rehearsal guards (SPEC §15.2).

Written but NEVER run here (coordination note N5): the integrating engineer
runs the ``postgres`` marker in the shared sandbox.  Tests 49, 51 and 54 come
from the Phase-B implementer; 48, 50, 52, 53 and 55 were added by the Assembly
step and drive the orchestrator, the target guard and the report artifact.
"""

import json
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection, connections

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.batch_accounting import LegacyBatchConflictError, verify_batch_chains
from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
from apps.legacy_import.services.ledger import (
    LegacyLedgerBusyError,
    LegacyLedgerConflictError,
    LegacyLedgerTargetError,
    LegacyLedgerTransitionError,
    TargetValidation,
    finish_run,
    upsert_entity_map,
)
from apps.legacy_import.services.ledger_locks import advisory_lock_key
from apps.legacy_import.services.rehearsal_authorizer import USER_MODEL_LABEL, build_target_validators
from apps.legacy_import.services.rehearsal_contracts import SOURCE_SYSTEM, EmailTrustPolicy
from apps.legacy_import.services.rehearsal_identity_phase import (
    IdentityCohortPhase,
    build_email_trust_policy,
    email_evidence_digest,
)
from apps.legacy_import.services.rehearsal_target_guard import (
    REHEARSAL_TARGET_GUC,
    REHEARSAL_TARGET_GUC_VALUE,
    assert_disposable_rehearsal_target,
)
from apps.legacy_import.tests.test_rehearsal_identity_phase import (
    _allow,
    _context,
    _factory,
    _plan,
    _policy,
    _row,
    _running_run,
    _staged_user,
)
from apps.legacy_import.tests.test_rehearsal_orchestrator import _organization as _orchestrator_organization
from apps.legacy_import.tests.test_rehearsal_orchestrator import _run_rehearsal, build_rehearsal_target
from apps.organizations.models import Organization
from core.constants import OrganizationType

pytestmark = [pytest.mark.postgres, pytest.mark.django_db]


@pytest.fixture()
def rehearsal_target(monkeypatch, tmp_path):
    """The orchestrator harness, rebuilt here so the plan patch is shared."""

    return build_rehearsal_target(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def _postgresql_only():
    if connection.vendor != "postgresql":
        pytest.skip("Rehearsal ledger/staging guards require PostgreSQL")


def _organization(code):
    owner = get_user_model().objects.create_superuser(
        username=f"rehearsal_pg_{code}_actor",
        email=f"rehearsal-pg-{code}@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name=f"Rehearsal PG {code.title()} Organization",
        slug=f"rehearsal-pg-{code}-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    return organization, owner


def _staging_policy():
    return _policy(
        email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST,
        email_trust_manifest_digest="b" * 64,
        max_staged_accounts=2,
        student_role_name="student",
        worker_role_name="teacher",
    )


def _staging_context(organization, actor, run, policy, *, target_validators):
    manifest = frozenset(
        {
            email_evidence_digest("student-1@example.test"),
            email_evidence_digest("worker-1@example.test"),
        }
    )
    return _context(
        plan=_plan(students=1, workers=1),
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
        email_policy=build_email_trust_policy(policy, manifest),
        target_validators=target_validators,
    )


def test_nested_atomic_stage_and_ledger_write_is_all_or_nothing():
    """SPEC §15.2/49 — a failed ledger write must undo the staged account."""

    organization, actor = _organization("atomic")
    policy = _staging_policy()
    plan = _plan(students=1, workers=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=2)
    refusing_validators = {
        USER_MODEL_LABEL: lambda **_kwargs: TargetValidation(exists=False, organization_matches=True)
    }

    with pytest.raises(LegacyLedgerTargetError) as exc_info:
        IdentityCohortPhase().run(
            _staging_context(organization, actor, run, policy, target_validators=refusing_validators)
        )

    assert exc_info.value.code == "legacy_target_not_found"
    assert get_user_model()._default_manager.filter(username="myedu.student.1").exists() is False
    assert LegacyEntityMap.objects.filter(organization=organization).exists() is False
    assert LegacyEntityObservation.objects.filter(run=run).exists() is False
    assert LegacyImportBatch.objects.filter(run=run).exists() is False


def test_cross_tenant_ledger_write_is_denied():
    """SPEC §15.2/51 — a target owned by another tenant is never mapped."""

    organization, actor = _organization("tenant-a")
    foreign_organization, _foreign_actor = _organization("tenant-b")
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)
    foreign_user = get_user_model().objects.create_user(
        username="rehearsal_pg_foreign_target",
        email="rehearsal-pg-foreign-target@example.test",
        password="test-only",
    )
    profile = foreign_user.profile
    profile.organization = foreign_organization
    profile.save(update_fields=["organization", "updated_at"])

    with pytest.raises(LegacyLedgerTargetError) as exc_info:
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="student",
            legacy_pk="7421",
            source_row_hash="d" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
            target_pk=str(foreign_user.pk),
            target_validators=build_target_validators(),
        )

    assert exc_info.value.code == "legacy_target_cross_organization"
    assert LegacyEntityMap.objects.filter(organization=organization).exists() is False
    assert LegacyEntityObservation.objects.filter(run=run).exists() is False


def test_staged_accounts_are_locked_and_inactive():
    """SPEC §15.2/54 — staging never activates an account or sets a password."""

    organization, actor = _organization("staged")
    policy = _staging_policy()
    plan = _plan(students=1, workers=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=2)

    report = IdentityCohortPhase().run(
        _staging_context(organization, actor, run, policy, target_validators=build_target_validators())
    )

    assert report.staged_account_count == 2
    assert dict(report.state_counts) == {"migrated": 2, "skipped": 0, "quarantined": 0}
    observations = LegacyEntityObservation.objects.filter(run=run, state=LegacyEntityMap.State.MIGRATED)
    assert observations.count() == 2
    for observation in observations:
        staged = _staged_user(observation.target_pk)
        assert observation.target_model_label == USER_MODEL_LABEL
        assert staged.is_active is False
        assert staged.has_usable_password() is False
        assert staged.profile.access_state == UserProfile.AccessState.STAGED
        assert staged.profile.organization_id == organization.pk
        assert staged.memberships.get(organization=organization).is_active is False


def _rls_session(organization_id):
    """Mirror ``apps/legacy_import/tests/test_rls.py``: tenant context + app role."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', false)")
        cursor.execute("SELECT set_config('app.current_org_id', %s, false)", [str(organization_id)])
        cursor.execute("SELECT set_config('app.current_user_id', '', false)")
        cursor.execute("SET LOCAL ROLE rls_app_role")


@pytest.mark.django_db(transaction=True)
def test_advisory_lock_serialises_two_concurrent_rehearsals():
    """SPEC §15.2/48 — a scope already owned by another worker is refused.

    ``transaction=True`` şərtdir: wrapped-test rejimində setup-ın ledger
    çağırışları xact-advisory kilidini test transaksiyası boyu saxlayır və
    holder bağlantısı əbədi bloklanırdı (2026-08-26 self-deadlock insidenti).
    """

    organization, actor = _organization("advisory")
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)
    lock_key = advisory_lock_key(
        organization_id=organization.pk,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=run.snapshot_sha256,
        transform_version=run.transform_version,
    )

    holder = connections.create_connection("default")
    holder.set_autocommit(False)
    try:
        with holder.cursor() as cursor:
            # Reqressiya sığortası: kilid 5 saniyəyə alınmasa asılmaq əvəzinə xəta ver.
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])

        with pytest.raises(LegacyLedgerBusyError) as exc_info:
            upsert_entity_map(
                run_id=run.pk,
                actor=actor,
                authorize=_allow,
                entity_type="student",
                legacy_pk="1",
                source_row_hash="a" * 64,
                state=LegacyEntityMap.State.SKIPPED,
                target_validators=build_target_validators(),
            )
    finally:
        holder.rollback()
        holder.close()

    assert exc_info.value.code == "legacy_scope_busy"
    assert LegacyEntityObservation.objects.filter(run=run).exists() is False


def test_run_writes_only_under_tenant_rls_context():
    """SPEC §15.2/50 — the orchestrator's session context is what authorises writes."""

    organization, actor = _organization("rls-context")
    foreign_organization, _foreign_actor = _organization("rls-foreign")
    policy = _policy()
    plan = _plan(students=1)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=1)

    # A foreign tenant context under the restricted role must see nothing and
    # must not be able to append an observation to this run.
    _rls_session(foreign_organization.pk)
    assert LegacyMigrationRun.objects.filter(pk=run.pk).exists() is False
    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="student",
            legacy_pk="1",
            source_row_hash="b" * 64,
            state=LegacyEntityMap.State.SKIPPED,
            target_validators=build_target_validators(),
        )
    assert exc_info.value.code == "legacy_run_not_found"

    # The run's own tenant context — the one core.rls.set_rls_tenant installs —
    # is the only context under which the same write succeeds.
    _rls_session(organization.pk)
    entity_map = upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk="1",
        source_row_hash="b" * 64,
        state=LegacyEntityMap.State.SKIPPED,
        target_validators=build_target_validators(),
    )
    assert entity_map.organization_id == organization.pk
    assert LegacyEntityObservation.objects.filter(run=run).count() == 1


@pytest.mark.django_db(transaction=True)
def test_batch_chain_verifies_and_finish_run_is_fail_closed(rehearsal_target):
    """SPEC §15.2/52 — the chain replays and a short run can never succeed."""

    organization, actor = _orchestrator_organization("pg-chain")

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    run = LegacyMigrationRun.objects.get(pk=outcome.run_id)
    assert run.status == LegacyMigrationRun.Status.SUCCEEDED
    verify_batch_chains(run)

    tampered = LegacyImportBatch.objects.filter(run=run).order_by("source_table", "sequence").first()

    # Müdafiə lay 1 — adi bağlantı üçün batch sətri DB trigger-i ilə dəyişməzdir:
    # tamper cəhdinin özü rədd edilir (2026-08-26: test əvvəl bunu nəzərə almırdı).
    from django.db import DatabaseError as _DatabaseError
    from django.db import transaction as _transaction

    with pytest.raises(_DatabaseError, match="batch dəyişdirilə bilməz"):
        with _transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE legacy_import_legacyimportbatch SET source_digest = %s WHERE id = %s",
                    ["f" * 64, str(tampered.pk)],
                )

    # Müdafiə lay 2 — trigger-i keçə bilən DBA/superuser səviyyəli tamper belə
    # Python zəncir yoxlamasından gizlənə bilmir (fail-closed).
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE legacy_import_legacyimportbatch DISABLE TRIGGER USER")
        try:
            cursor.execute(
                "UPDATE legacy_import_legacyimportbatch SET source_digest = %s WHERE id = %s",
                ["f" * 64, str(tampered.pk)],
            )
        finally:
            cursor.execute("ALTER TABLE legacy_import_legacyimportbatch ENABLE TRIGGER USER")
    with pytest.raises(LegacyBatchConflictError) as exc_info:
        verify_batch_chains(LegacyMigrationRun.objects.get(pk=run.pk))
    assert exc_info.value.code == "legacy_batch_digest_invalid"

    # A run whose declared source rows exceed the sealed batches can never be
    # finished SUCCEEDED, even when every gate above it is asked to pass.
    short_organization, short_actor = _organization("pg-short")
    short_run = _running_run(
        short_organization,
        short_actor,
        policy=_policy(),
        plan=_plan(students=2),
        source_row_count=2,
    )
    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=short_run.pk,
            actor=short_actor,
            authorize=_allow,
            outcome=LegacyMigrationRun.Status.SUCCEEDED,
        )
    assert exc_info.value.code == "legacy_success_count_mismatch"


def test_target_guard_reads_real_disposable_marker():
    """SPEC §15.2/53 — check 7 needs a deliberate ALTER DATABASE on this DB."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [REHEARSAL_TARGET_GUC])
        marker = cursor.fetchone()[0]
    if (marker or "").strip() != REHEARSAL_TARGET_GUC_VALUE:
        pytest.skip("this database carries no emsarena.rehearsal_target marker")

    settings_object = SimpleNamespace(
        LEGACY_REHEARSAL_TARGET_DISPOSABLE=True,
        MANAGEMENT_COMMAND_ENVIRONMENT="test",
    )
    attestation = assert_disposable_rehearsal_target(settings_object=settings_object)

    assert attestation.disposable_marker is True
    assert attestation.role_is_superuser is False
    assert attestation.role_bypasses_rls is False
    assert attestation.rls_bypass_active is False
    assert len(attestation.migration_head_digest) == 64
    assert connection.settings_dict["NAME"] not in repr(attestation)
    assert connection.settings_dict["NAME"] not in str(attestation.to_safe_log_dict())


def test_two_clean_targets_produce_the_same_determinism_digest(rehearsal_target):
    """SPEC §15.2/55 — the digest binds evidence, never run/tenant identity.

    A second physical database is not available inside one test transaction, so
    the two rehearsals run under two independent tenants created BEFORE either
    pass, which keeps the pre-run identity baseline identical.  Everything the
    digest excludes (run pk, organization pk, timestamps, chain digests) still
    differs between them.
    """

    first_organization, first_actor = _orchestrator_organization("pg-target-one")
    second_organization, second_actor = _orchestrator_organization("pg-target-two")

    first = _run_rehearsal(rehearsal_target, first_organization, first_actor, ordinal=1)
    second = _run_rehearsal(
        rehearsal_target,
        second_organization,
        second_actor,
        ordinal=2,
        compare_report_path=first.report_path,
    )

    assert first.status == LegacyMigrationRun.Status.SUCCEEDED
    assert second.status == LegacyMigrationRun.Status.SUCCEEDED
    assert second.determinism_digest == first.determinism_digest
    assert second.run_id != first.run_id

    first_document = json.loads(open(first.report_path, encoding="ascii").read())
    second_document = json.loads(open(second.report_path, encoding="ascii").read())
    assert first_document["deterministic"] == second_document["deterministic"]
    assert first_document["provenance"]["run_id"] != second_document["provenance"]["run_id"]
    assert first_document["provenance"]["organization_id"] != second_document["provenance"]["organization_id"]
    assert first_document["provenance"]["batch_chain_digests"] != second_document["provenance"]["batch_chain_digests"]


def test_phase_a_attestation_issue_is_bound_to_the_run(rehearsal_target):
    """The Phase-A evidence digest must land in the RLS-protected ledger."""

    organization, actor = _orchestrator_organization("pg-attestation")

    outcome = _run_rehearsal(rehearsal_target, organization, actor)

    issue = LegacyMigrationIssue.objects.get(
        run_id=outcome.run_id,
        rule_code="legacy_rehearsal_attestation",
    )
    assert issue.severity == LegacyMigrationIssue.Severity.INFO
    assert issue.entity_map_id is None
    assert issue.source_table == "rehearsal"
    assert issue.legacy_pk == "phase-a"
    assert len(issue.payload_digest) == 64
