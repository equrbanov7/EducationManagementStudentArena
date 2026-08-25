"""PostgreSQL-only rehearsal guards (SPEC §15.2 and FAZA 3 §8/7-10).

Written but NEVER run here (coordination note N5 / FAZA 3 V-5): the integrating
engineer runs the ``postgres`` marker in the shared sandbox.  Tests 49, 51 and
54 come from the Phase-B implementer; 48, 50, 52, 53 and 55 were added by the
Assembly step and drive the orchestrator, the target guard and the report
artifact.  The final block belongs to the FAZA 3 structure + placement slice and
proves the two findings that made it defer ``StudentAcademicRecord`` (B-1, B-2)
plus the tenant guards its new targets live behind.
"""

import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, connection, connections, transaction

import pytest

from apps.accounts.identity_models import AccountActivationEvidence
from apps.accounts.models import UserProfile
from apps.accounts.public import activate_staged_account
from apps.accounts.services.identity_access import IdentityAccessError, stage_imported_account
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
from apps.legacy_import.services.rehearsal_catalog_phase import AcademicCatalogPhase
from apps.legacy_import.services.rehearsal_contracts import SOURCE_SYSTEM, EmailTrustPolicy
from apps.legacy_import.services.rehearsal_identity_phase import (
    IdentityCohortPhase,
    build_email_trust_policy,
    email_evidence_digest,
)
from apps.legacy_import.services.rehearsal_sar_targets import ACTIVATION_REASON_CODE, activation_evidence_digest
from apps.legacy_import.services.rehearsal_structure_phase import AcademicStructurePhase
from apps.legacy_import.services.rehearsal_target_guard import (
    REHEARSAL_TARGET_GUC,
    REHEARSAL_TARGET_GUC_VALUE,
    assert_disposable_rehearsal_target,
)
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256
from apps.legacy_import.tests.test_rehearsal_catalog_phase import _structured_context as _catalog_context
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
from apps.legacy_import.tests.test_rehearsal_structure_phase import _full_context, _full_plan
from apps.legacy_import.tests.test_rehearsal_structure_phase import _policy as _structure_policy
from apps.legacy_import.tests.test_rehearsal_structure_phase import _running_run as _structure_run
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

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
    with pytest.raises(DatabaseError, match="batch dəyişdirilə bilməz"):
        with transaction.atomic():
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


# ---------------------------------------------------------------------------
# FAZA 3 — SLICE 1 (SPEC §8/7-10): the academic_structure + student_placement
# slice's PostgreSQL guards.  Also written but never run here (V-5).
# ---------------------------------------------------------------------------

_SAR_INSERT = (
    "INSERT INTO registrar_studentacademicrecord "
    "(id, created_at, updated_at, organization_id, student_id, program_id, "
    " curriculum_id, group_id, admission_year, status, is_active) "
    "VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, %s, NULL, 2019, 'enrolled', TRUE)"
)


def _university_role(organization, *, name="student"):
    """One active tenant role ``stage_imported_account`` can bind a member to."""

    return Role.objects.create(
        organization=organization,
        name=name,
        display_name=name.title(),
        level=10,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=[],
        is_active=True,
    )


def _stage(organization, actor, suffix):
    return stage_imported_account(
        organization=organization,
        role=_university_role(organization, name=f"student-{suffix}"),
        actor=actor,
        username=f"myedu.student.{suffix}",
        email=f"myedu-student-{suffix}@example.test",
        student_identifier=suffix,
    ).user


def test_student_academic_record_rejects_staged_member():
    """SPEC §8/7 — the executable justification for D-6 (finding B-1).

    Canlı ``registrar_member_has_permission`` (0042-nin əvəzləməsi) boş
    permission-da belə ÜÇ aktivlik şərtini tələb edir: membership.is_active,
    role.is_active VƏ actor(auth_user).is_active.  Rehearsal-staged hesabda
    həm user, həm membership qeyri-aktivdir → SAR insert-i 23514 ilə rədd
    olunur.  Üstəlik staged user-in is_active-i birbaşa qaldırıla bilməz
    (accounts_staged_user_must_remain_inactive) — blokada ikiqatdır, buna görə
    bu dilim sıfır ``StudentAcademicRecord`` yaradır.  Membership-predikatı
    ayrıca, NORMAL (staged olmayan) istifadəçi ilə izolə edilib yoxlanır.
    """

    organization, actor = _organization("sar-staged")
    staged = _stage(organization, actor, "b1")

    # The two facts the guard's predicate actually reads.
    assert staged.is_active is False
    membership = Membership.objects.get(user=staged, organization=organization)
    assert membership.is_active is False

    speciality = OrgUnit.objects.create(
        organization=organization,
        slug="myedu-spec-b1",
        unit_type=OrgUnitType.SPECIALTY,
        name="İxtisas B1",
    )
    program = Program.objects.create(
        organization=organization,
        specialty_unit=speciality,
        code="B1-050620",
        name="İxtisas B1",
        degree_level="bachelor",
        ects_total=240,
    )
    # B-2: ``curriculum`` is NOT nullable, so even the REFUSED insert needs one —
    # which is the second reason SAR materialisation waits for the curricula slice.
    curriculum = Curriculum.objects.create(organization=organization, program=program, admission_year=2019)
    arguments = [str(organization.pk), staged.pk, str(program.pk), str(curriculum.pk)]

    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(_SAR_INSERT, arguments)

    assert "lacks an active authorized membership: student" in str(exc_info.value)

    # Staged hesabda TƏKCƏ membership-i aktivləşdirmək kifayət etmir — canlı
    # predikat actor.is_active-i də tələb edir (ikiqat blokada sübutu).
    assert Membership.objects.filter(pk=membership.pk).update(is_active=True) == 1
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(_SAR_INSERT, arguments)
    staged.refresh_from_db()
    assert staged.is_active is False

    # Membership-predikatını NORMAL istifadəçi ilə izolə et: aktiv user +
    # qeyri-aktiv üzvlük → rədd; üzvlük aktivləşəndə → keçir.
    normal = get_user_model().objects.create_user(
        username="b1_normal_student", email="b1-normal@example.test", password="test-only"
    )
    normal_membership = Membership.objects.create(
        organization=organization,
        user=normal,
        role=_university_role(organization, name="student-b1-normal"),
        is_active=False,
        is_primary=False,
    )
    normal_arguments = [str(organization.pk), normal.pk, str(program.pk), str(curriculum.pk)]
    with pytest.raises(DatabaseError) as normal_exc:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(_SAR_INSERT, normal_arguments)
    assert "lacks an active authorized membership: student" in str(normal_exc.value)
    assert Membership.objects.filter(pk=normal_membership.pk).update(is_active=True) == 1
    with connection.cursor() as cursor:
        cursor.execute(_SAR_INSERT, normal_arguments)


def test_structure_phase_writes_under_rls():
    """SPEC §8/8 — OrgUnit/Program are written with a tenant context only.

    ``bypass_rls`` is never entered: the phase writes under the restricted
    ``rls_app_role`` with ``app.current_org_id`` set, and a second tenant's
    session then sees none of the rows it created.
    """

    organization, actor = _organization("structure-rls")
    foreign_organization, _foreign_actor = _organization("structure-rls-foreign")
    policy = _structure_policy()
    plan = _full_plan()
    run = _structure_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    context = replace(_full_context(organization, actor, policy=policy, plan=plan), run_id=run.pk)

    _rls_session(organization.pk)
    report = AcademicStructurePhase().run(context)

    assert report.phase_key == "academic_structure"
    assert dict(report.state_counts) == {"migrated": 13, "skipped": 0, "quarantined": 1}
    # 5 departments (the type-9 row is quarantined) + 3 specialities + 5 groups.
    assert OrgUnit.objects.filter(organization=organization).count() == 13
    # One program per (speciality, observed degree): 10→bachelor+master, 11, 12.
    assert Program.objects.filter(organization=organization).count() == 4

    # The very same restricted role under another tenant sees nothing at all.
    _rls_session(foreign_organization.pk)
    assert OrgUnit.objects.count() == 0
    assert Program.objects.count() == 0


def test_program_specialty_unit_cross_org_rejected():
    """SPEC §8/9 — 0041 ``registrar_same_org_specialty_unit_guard`` fires.

    The structure phase always creates a Program under the SAME organization as
    its speciality unit; this proves the database refuses the alternative, so a
    future cross-tenant derivation bug could never be silently persisted.
    """

    organization, _actor = _organization("program-same-org")
    foreign_organization, _foreign_actor = _organization("program-foreign-org")
    foreign_speciality = OrgUnit.objects.create(
        organization=foreign_organization,
        slug="myedu-spec-foreign",
        unit_type=OrgUnitType.SPECIALTY,
        name="Yad İxtisas",
    )

    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            Program.objects.create(
                organization=organization,
                specialty_unit=foreign_speciality,
                code="X-050620",
                name="Yad İxtisas",
                degree_level="bachelor",
                ects_total=240,
            )

    assert "must belong to the same organization: specialty_unit" in str(exc_info.value)
    assert Program.objects.filter(organization=organization).exists() is False


def test_profile_fin_unique_and_staged_profile_writable():
    """SPEC §8/10 — ``fin`` is writable on a staged profile; activation is not.

    The placement phase writes ``UserProfile.fin`` on accounts the identity
    phase staged.  ``accounts_reject_active_staged_profile_trg`` fires BEFORE
    INSERT OR UPDATE on the whole row, so this proves the FİN write passes it
    while an ``access_state`` flip on the same row still does not.
    """

    organization, actor = _organization("fin-staged")
    first = _stage(organization, actor, "fin1")
    second = _stage(organization, actor, "fin2")

    # Two NULL FİNs coexist under the GLOBAL unique index (nullable-unique).
    assert UserProfile.objects.filter(user__in=(first, second), fin__isnull=True).count() == 2

    # Exactly the write the placement phase performs: an UPDATE on a staged row.
    assert UserProfile.objects.filter(user=first).update(fin="5JFC0RE") == 1
    profile = UserProfile.objects.get(user=first)
    assert profile.fin == "5JFC0RE"
    assert profile.access_state == UserProfile.AccessState.STAGED

    # A FİN is a national identifier, so the uniqueness is deliberately global
    # rather than per-tenant — a second account may never claim the same one.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            UserProfile.objects.filter(user=second).update(fin="5JFC0RE")

    # …and none of that weakens the activation gate on the very same row.
    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            UserProfile.objects.filter(user=first).update(access_state=UserProfile.AccessState.ACTIVE)

    assert "accounts_staged_activation_service_required" in str(exc_info.value)
    assert UserProfile.objects.get(user=first).access_state == UserProfile.AccessState.STAGED


# ---------------------------------------------------------------------------
# FAZA 3 — SLICE 2 (SPEC §10 items 8-13): the activation bridge that discharges
# B-1/B-3, the catalogue under RLS and the two curriculum guards that justify
# the §5.5 matrix.  Written but NEVER run here (V-5): the integrating engineer
# drives the ``postgres`` marker in the shared sandbox.
# ---------------------------------------------------------------------------

_ACTIVATION_TRANSFORM_VERSION = "rehearsal-identity-v1.000000000000"
_ACTIVATION_FUNCTION = "SELECT public.accounts_activate_staged_identity(%s, %s, %s, %s, %s, %s, %s)"


def _staged_pair(organization, actor, suffix, *, email=None):
    """One staged account plus the role it was staged with (activation needs both)."""

    role = _university_role(organization, name=f"student-{suffix}")
    staged = stage_imported_account(
        organization=organization,
        role=role,
        actor=actor,
        username=f"myedu.student.{suffix}",
        email=f"myedu-student-{suffix}@example.test" if email is None else email,
        student_identifier=suffix,
    ).user
    return staged, role


def _activate(staged, role, organization, actor, legacy_pk):
    """The SAR phase's activation call, verbatim (E-10 / §3.10)."""

    return activate_staged_account(
        user=staged,
        organization=organization,
        expected_role=role,
        actor=actor,
        email_authoritative=True,
        email_authority_evidence_digest=activation_evidence_digest(
            transform_version=_ACTIVATION_TRANSFORM_VERSION,
            snapshot_sha256=SOURCE_SNAPSHOT_SHA256,
            legacy_pk=legacy_pk,
        ),
        email_authority_reason_code=ACTIVATION_REASON_CODE,
    )


def _speciality_program(organization, code):
    speciality = OrgUnit.objects.create(
        organization=organization,
        slug=f"myedu-spec-{code.lower()}",
        unit_type=OrgUnitType.SPECIALTY,
        name=f"İxtisas {code}",
    )
    return Program.objects.create(
        organization=organization,
        specialty_unit=speciality,
        code=code,
        name=f"İxtisas {code}",
        degree_level="bachelor",
        ects_total=240,
    )


def test_staged_student_activation_unblocks_student_record():
    """SPEC §10/8 — the executable B-1/B-3 discharge.

    Nothing about ``registrar_member_has_permission`` is weakened: the SAME raw
    insert that 0041/0042 refuse for a staged account is accepted the moment
    ``activate_staged_account`` has run.  The precondition V-11 discovered is
    asserted first — the staged cohort carries a non-blank (merely untrusted)
    legacy email, so the ``BTRIM(email) <> ''`` gate is passed by construction.
    """

    organization, actor = _organization("sar-activation")
    staged, role = _staged_pair(organization, actor, "b3")
    assert staged.email.strip() != ""  # V-11's precondition, stated as an assertion

    program = _speciality_program(organization, "B3-050620")
    curriculum = Curriculum.objects.create(organization=organization, program=program, admission_year=2019)
    arguments = [str(organization.pk), staged.pk, str(program.pk), str(curriculum.pk)]

    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(_SAR_INSERT, arguments)
    assert "lacks an active authorized membership: student" in str(exc_info.value)

    result = _activate(staged, role, organization, actor, 4711)

    assert result.activated is True
    staged.refresh_from_db()
    assert staged.is_active is True
    assert UserProfile.objects.get(user=staged).access_state == UserProfile.AccessState.ACTIVE
    membership = Membership.objects.get(user=staged, organization=organization)
    assert (membership.is_active, membership.is_primary) == (True, True)

    # V-12: after activation every conjunct of the live predicate holds, so the
    # very same statement now succeeds — with zero trigger changes.
    with connection.cursor() as cursor:
        cursor.execute(_SAR_INSERT, arguments)
    assert StudentAcademicRecord.objects.filter(organization=organization, student=staged).count() == 1

    # The append-only evidence row is committed AND consumed (never left NULL).
    evidence = AccountActivationEvidence.objects.get(organization=organization, user_ref=str(staged.pk))
    assert evidence.reason_code == ACTIVATION_REASON_CODE
    assert evidence.role_ref == str(role.pk)
    assert evidence.consumed_at is not None
    assert evidence.evidence_digest == activation_evidence_digest(
        transform_version=_ACTIVATION_TRANSFORM_VERSION,
        snapshot_sha256=SOURCE_SNAPSHOT_SHA256,
        legacy_pk=4711,
    )


def test_activation_requires_non_blank_email():
    """SPEC §10/9 — pin V-11's precondition on BOTH sides of the seam.

    The Python mirror refuses first; calling the SECURITY DEFINER surface
    directly proves the database refuses the same row on its own, so a future
    change to the staging path cannot silently unblock a blank-email account.
    """

    organization, actor = _organization("blank-email")
    staged, role = _staged_pair(organization, actor, "blank", email="")
    assert staged.email == ""

    with pytest.raises(IdentityAccessError) as python_exc:
        _activate(staged, role, organization, actor, 4712)
    assert str(python_exc.value) == "identity_authoritative_email_missing"

    with pytest.raises(DatabaseError) as database_exc:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Mirror apps/accounts/tests/test_identity_access_postgres.py:359-361 —
                # the SECURITY DEFINER function's own actor-context guard (line 18 of
                # its body) raises accounts_activation_actor_context_mismatch before
                # the email check ever runs unless app.current_user_id matches the
                # actor we're invoking it as.
                cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
                cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(organization.pk)])
                cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(actor.pk)])
                cursor.execute(
                    _ACTIVATION_FUNCTION,
                    [
                        str(uuid.uuid4()),
                        staged.pk,
                        str(organization.pk),
                        str(role.pk),
                        actor.pk,
                        "a" * 64,
                        ACTIVATION_REASON_CODE,
                    ],
                )
    assert "accounts_activation_authoritative_email_missing" in str(database_exc.value)

    staged.refresh_from_db()
    assert staged.is_active is False
    assert UserProfile.objects.get(user=staged).access_state == UserProfile.AccessState.STAGED
    assert AccountActivationEvidence.objects.filter(organization=organization).exists() is False


def test_catalog_phase_writes_under_rls():
    """SPEC §10/10 — Subject/Curriculum/CurriculumSubject under a tenant context.

    ``bypass_rls`` is never entered: the catalogue phase writes under the
    restricted ``rls_app_role`` with ``app.current_org_id`` set, and a second
    tenant's session then sees none of the rows it created.
    """

    organization, actor = _organization("catalog-rls")
    foreign_organization, _foreign_actor = _organization("catalog-rls-foreign")
    # The structure phase runs first in the SAME run: the catalogue resolves its
    # Programs from THIS run's ``speciality_program`` maps and mints none itself.
    context, _run = _catalog_context(organization, actor)

    _rls_session(organization.pk)
    report = AcademicCatalogPhase().run(context)

    assert report.phase_key == "academic_catalog"
    # V-20 moved curriculum 101 out of quarantine (to_date-minus-duration now
    # resolves its admission year instead of giving up), so the shared fixture
    # migrates one more row and quarantines one fewer than before.
    assert dict(report.state_counts) == {"migrated": 14, "skipped": 0, "quarantined": 3}
    assert report.staged_account_count == 14
    assert Subject.objects.filter(organization=organization).count() == 4
    assert Curriculum.objects.filter(organization=organization).count() == 1
    assert CurriculumSubject.objects.filter(organization=organization).count() == 6

    _rls_session(foreign_organization.pk)
    assert Subject.objects.count() == 0
    assert Curriculum.objects.count() == 0
    assert CurriculumSubject.objects.count() == 0


def test_curriculum_program_coherence_rejects_mismatch():
    """SPEC §10/11 — the executable justification for the §5.5 M2 rule.

    ``registrar_guard_student_record_coherence`` (0041) refuses a SAR whose
    curriculum belongs to a different program, which is exactly why a legacy
    curriculum whose program contradicts the placement may never be adopted.
    """

    organization, actor = _organization("sar-coherence")
    student, role = _staged_pair(organization, actor, "m2")
    _activate(student, role, organization, actor, 4713)

    placement_program = _speciality_program(organization, "M2-050620")
    other_program = _speciality_program(organization, "M2-060730")
    foreign_curriculum = Curriculum.objects.create(
        organization=organization, program=other_program, admission_year=2019
    )

    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    _SAR_INSERT,
                    [str(organization.pk), student.pk, str(placement_program.pk), str(foreign_curriculum.pk)],
                )
    assert "student record curriculum must belong to its program" in str(exc_info.value)
    assert StudentAcademicRecord.objects.filter(organization=organization).exists() is False

    # The fallback the matrix prescribes — a curriculum under the PLACEMENT
    # program — is accepted, so ``synthesise`` can never write an incoherent row.
    coherent = Curriculum.objects.create(organization=organization, program=placement_program, admission_year=2019)
    with connection.cursor() as cursor:
        cursor.execute(_SAR_INSERT, [str(organization.pk), student.pk, str(placement_program.pk), str(coherent.pk)])
    assert StudentAcademicRecord.objects.filter(organization=organization).count() == 1


def test_curriculum_program_immutable_after_dependents():
    """SPEC §10/12 — 0045's conditional guard freezes ``Curriculum.program``.

    This is why §5.1 warns that a wrong merge cannot be repaired in place: the
    moment one plan row (or one SAR) references the curriculum, its program is
    frozen and the only remedy is rebuilding the disposable target.
    """

    organization, _actor = _organization("curriculum-frozen")
    first_program = _speciality_program(organization, "CF-050620")
    second_program = _speciality_program(organization, "CF-060730")
    curriculum = Curriculum.objects.create(organization=organization, program=first_program, admission_year=2019)

    # With no dependent evidence the guard returns early and the move is allowed.
    assert Curriculum.objects.filter(pk=curriculum.pk).update(program=second_program) == 1
    assert Curriculum.objects.filter(pk=curriculum.pk).update(program=first_program) == 1

    subject = Subject.objects.create(organization=organization, code="MYEDU-L1", name="Riyaziyyat", ects=6)
    CurriculumSubject.objects.create(
        organization=organization,
        curriculum=curriculum,
        subject=subject,
        semester_number=1,
        is_elective=False,
        elective_group="",
        required_choices=1,
        order=0,
    )

    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            Curriculum.objects.filter(pk=curriculum.pk).update(program=second_program)

    assert "registrar parent identity has dependent evidence" in str(exc_info.value)
    curriculum.refresh_from_db()
    assert curriculum.program_id == first_program.pk


def test_activated_profile_flags_are_writable():
    """SPEC §10/13 — E-11's two writes land on an already-active profile.

    Activation asserts *the registry says this person exists*, never *this email
    is verified*: both flags are flipped in the same atomic block so the legacy
    address cannot be used for recovery and the account lands in the existing
    first-login flow.  ``accounts_reject_active_staged_profile`` only guards the
    staged→non-staged transition, which is asserted to still hold.
    """

    organization, actor = _organization("profile-flags")
    active_user, role = _staged_pair(organization, actor, "e11")
    _activate(active_user, role, organization, actor, 4714)

    updated = UserProfile.objects.filter(user=active_user, organization=organization).update(
        email_verified=False, password_change_required=True
    )
    assert updated == 1
    profile = UserProfile.objects.get(user=active_user)
    assert (profile.email_verified, profile.password_change_required) == (False, True)
    assert profile.access_state == UserProfile.AccessState.ACTIVE

    # The very same two writes on a STAGED row are unguarded too…
    staged, _staged_role = _staged_pair(organization, actor, "e11b")
    assert UserProfile.objects.filter(user=staged).update(email_verified=False, password_change_required=True) == 1

    # …while flipping ``access_state`` outside the activation service still is not.
    with pytest.raises(DatabaseError) as exc_info:
        with transaction.atomic():
            UserProfile.objects.filter(user=staged).update(access_state=UserProfile.AccessState.ACTIVE)

    assert "accounts_staged_activation_service_required" in str(exc_info.value)
    assert UserProfile.objects.get(user=staged).access_state == UserProfile.AccessState.STAGED
