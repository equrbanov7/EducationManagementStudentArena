"""Phase ``worker_materialisation`` tests: V-22..V-27, digest seam, ortaq kap."""

import hashlib
from dataclasses import replace

from django.contrib.auth import get_user_model

import pytest

from apps.accounts.models import UserProfile
from apps.accounts.public import stage_imported_account
from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.field_contracts import WORKER_IDENTITY_FIELDS, is_credential_field
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    STUDENT_RECORD_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_target_validators,
)
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
    encoded_part,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.rehearsal_sar_targets import SAR_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_worker_phase import (
    DERIVED_DIGEST_NAMESPACE,
    WORKER_PHASE_KEY,
    WorkerMaterialisationPhase,
)
from apps.legacy_import.services.rehearsal_worker_targets import (
    ACTIVATION_REASON_CODE,
    ISSUE_SEVERITY,
    WORKER_MATERIALISATION_ENTITY_TYPE,
    worker_activation_evidence_digest,
    worker_derivation_hash,
)
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable, LegacySourceExtractionError
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType

_WORKER_ENTITY_TYPE = "worker"
_WORKER_ROLE_NAME = "teacher"
_PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "worker_materialisation",
    "sar_materialisation",
)
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "pin_for_lock")
_SOURCE_COLUMNS = (*WORKER_IDENTITY_FIELDS.allowed_fields, *_CREDENTIAL_COLUMNS)


# ---------------------------------------------------------------------------
# Fake source (same shape as the identity/placement/sar fixtures)
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Positional DB-API cursor over already-projected source values."""

    def __init__(self, description, rows):
        self.description = description
        self._rows = list(rows)
        self._position = 0

    def fetchmany(self, size):
        chunk = self._rows[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def close(self):
        return None


class _FakeSourceConnection:
    """Read-only source that only ever returns contract-projected columns."""

    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.rolled_back = False
        self.closed = False

    def server_is_read_only(self):
        return True

    def begin_read_only_snapshot(self):
        return None

    def session_is_read_only(self):
        return True

    def discover_table(self, source_table):
        return LegacyDiscoveredTable(
            source_table=source_table,
            column_names=_SOURCE_COLUMNS,
            primary_key_fields=("id",),
        )

    def open_compiled_select(self, query):
        self.statements.append(query.mysql_statement())
        field_names = query.projection.field_names
        return _FakeCursor(
            tuple((field_name, None, None, None, None, None, None) for field_name in field_names),
            [tuple(row[field_name] for field_name in field_names) for row in self.rows],
        )

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _factory(rows):
    connections = []

    def build():
        connection = _FakeSourceConnection(rows)
        connections.append(connection)
        return connection

    build.connections = connections
    return build


def _worker_row(legacy_pk, **overrides):
    values = {field_name: None for field_name in _SOURCE_COLUMNS}
    values["id"] = legacy_pk
    values["department_id"] = 5
    values["teacher_type"] = 1
    values["inzibati"] = 0
    values["password"] = "hunter2-raw-credential"
    values["pin_for_lock"] = "0000"
    values.update(overrides)
    return values


def _plan(workers):
    from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=workers,
        entries=(replace(canonical.entry_for("workers"), expected_rows=workers),),
    )


def _policy(**overrides):
    values = {
        "phase_keys": _PHASE_KEYS,
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.DENY_ALL,
        "email_trust_manifest_digest": "",
        "batch_rows": DEFAULT_BATCH_ROWS,
        "source_chunk_size": 1_000,
        "max_staged_accounts": 100,
        "student_role_name": "student",
        "worker_role_name": _WORKER_ROLE_NAME,
        "stage_and_activate": True,
        "max_activated_accounts": 50,
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _allow(**_kwargs):
    return True


def _context(*, plan, factory, policy=None, run_id=None, organization=None, actor=None, cancelled=None, notes=None):
    return RehearsalContext(
        run_id=run_id,
        organization=organization,
        actor=actor,
        authorize=_allow,
        target_validators=build_target_validators(),
        policy=policy or _policy(),
        plan=plan,
        source_connection_factory=factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=cancelled if cancelled is not None else (lambda: False),
        stdout_note=(notes if notes is not None else []).append,
    )


# ---------------------------------------------------------------------------
# Pure shape / taxonomy (no database)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_shape():
    phase = WorkerMaterialisationPhase()

    assert phase.phase_key == WORKER_PHASE_KEY and phase.order == 26
    assert phase.source_tables == () and phase.entity_types == (WORKER_MATERIALISATION_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(3)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "worker_materialised"
    assert phase.derived_state_key("skipped") == "worker_deferred"
    assert phase.derived_state_key("quarantined") == "worker_unresolved"


def test_issue_severity_map_covers_exactly_the_worker_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_worker_department_unresolved": "warning",
        "legacy_worker_activation_cap_reached": "warning",
        "legacy_worker_activation_refused": "warning",
        "legacy_worker_scope_refused": "warning",
        "legacy_worker_administrative_flag": "info",
        "legacy_worker_type_unknown": "info",
        "legacy_worker_scope_preexisting": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    # ``LegacyMigrationIssue`` (run, "workers", legacy_pk, rule_code) üzrə
    # unikaldır və identity fazası eyni cədvəl altında ``legacy_account_*``
    # yazır — kodlar prefikslə ayrılır.
    assert all(rule_code.startswith("legacy_worker_") for rule_code in ISSUE_SEVERITY)


def test_the_worker_contract_already_projects_the_three_facts():
    """Kontrakt DƏYİŞMİR: barmaq izi sabit qalır (mənbə faktları bölməsi)."""

    assert {"department_id", "teacher_type", "inzibati"} <= set(WORKER_IDENTITY_FIELDS.allowed_fields)
    assert not any(is_credential_field(field_name) for field_name in WORKER_IDENTITY_FIELDS.allowed_fields)


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        WorkerMaterialisationPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [
        ("worker_materialisation",),
        ("identity_cohort", "worker_materialisation"),
        ("academic_structure", "worker_materialisation"),
    ],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        WorkerMaterialisationPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_a_cancellation_request_stops_the_phase_before_it_reads_anything():
    factory = _factory([_worker_row(1)])
    context = _context(plan=_plan(1), factory=factory, cancelled=lambda: True)

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        WorkerMaterialisationPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert factory.connections == []


def test_the_worker_activation_evidence_digest_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-activation-evidence-v1\x00")
    for part in ("rehearsal-identity-v1.abcdef012345", "a" * 64, "worker", "17"):
        digest.update(encoded_part(part))

    assert (
        worker_activation_evidence_digest(
            transform_version="rehearsal-identity-v1.abcdef012345",
            snapshot_sha256="a" * 64,
            legacy_pk=17,
        )
        == digest.hexdigest()
    )
    assert ACTIVATION_REASON_CODE == "signed_authoritative_export"
    # Eyni legacy_pk-lı tələbə və işçi heç vaxt eyni sübutu bölüşmür.
    from apps.legacy_import.services.rehearsal_sar_targets import activation_evidence_digest

    assert digest.hexdigest() != activation_evidence_digest(
        transform_version="rehearsal-identity-v1.abcdef012345",
        snapshot_sha256="a" * 64,
        legacy_pk=17,
    )


def test_the_worker_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-worker-derivation-v1\x00")
    for part in (
        WORKER_IDENTITY_FIELDS.fingerprint,
        "1",
        "b" * 64,
        "materialised",
        "myedu-dep-5",
        "written",
        "1",
        "0",
        "activated",
        # 2026-08-28: ad yazısının vəziyyəti də qərarın kimliyinin bir
        # hissəsidir (boş adı doldurmaq ≠ mövcud adı qorumaq).
        "written",
        # Ata adı AYRI qərardır (ayrı hədəf sütun, ayrı mənbə sahəsi).
        "preserved",
    ):
        digest.update(encoded_part(part))

    computed = worker_derivation_hash(
        legacy_pk=1,
        row_hash="b" * 64,
        outcome_token="materialised",
        department_slug="myedu-dep-5",
        scope_state="written",
        teacher_type_text="1",
        inzibati_text="0",
        activation_state="activated",
        name_state="written",
        patronymic_state="preserved",
    )

    assert computed == digest.hexdigest()
    # Aktivasiya qərarı kimliyin bir hissəsidir: bir run-un aktivləşdirdiyi və
    # başqasının mənimsədiyi sətir EYNİ hash-lənməməlidir.
    assert computed != worker_derivation_hash(
        legacy_pk=1,
        row_hash="b" * 64,
        outcome_token="materialised",
        department_slug="myedu-dep-5",
        scope_state="written",
        teacher_type_text="1",
        inzibati_text="0",
        activation_state="preexisting",
    )


# ---------------------------------------------------------------------------
# Ledger-backed environment
# ---------------------------------------------------------------------------


@pytest.fixture()
def worker_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="worker_phase_actor",
        email="worker-phase-actor@example.test",
        password="test-only",
    )


def _organization(actor, slug):
    organization = Organization.objects.create(
        name=f"Worker {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    Role.objects.get_or_create(
        organization=organization,
        name=_WORKER_ROLE_NAME,
        defaults={"display_name": "Müəllim", "level": 40, "permissions": [], "is_active": True},
    )
    Role.objects.filter(organization=organization, name=_WORKER_ROLE_NAME).update(is_active=True)
    return organization


def _running_run(organization, actor, *, policy, plan):
    from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION

    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=plan.source_snapshot_sha256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=plan.expected_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{plan.fingerprint[:12]}",
        transform_version=policy.transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _seed_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _map(run_id, actor, *, entity_type, legacy_pk, label="", target_pk="", state=LegacyEntityMap.State.MIGRATED):
    return upsert_entity_map(
        run_id=run_id,
        actor=actor,
        authorize=_allow,
        entity_type=entity_type,
        legacy_pk=str(legacy_pk),
        source_row_hash=_seed_hash(f"{entity_type}:{legacy_pk}"),
        state=state,
        target_model_label=label,
        target_pk=str(target_pk),
        target_validators=build_target_validators(),
    )


def _seed_departments(organization, legacy_pks=(5, 6)):
    """``academic_structure``-un qoyub getdiyi kafedra OrgUnit-ləri (V-24)."""

    units = {}
    for legacy_pk in legacy_pks:
        units[legacy_pk] = OrgUnit.objects.create(
            organization=organization,
            slug=f"myedu-dep-{legacy_pk}",
            unit_type=OrgUnitType.CHAIR,
            name=f"Kafedra {legacy_pk}",
            settings={"legacy": {"table": "departments", "id": legacy_pk}},
        )
    return units


def _stage_workers(organization, actor, run_id, legacy_pks, *, blank_email=()):
    staged = {}
    role = Role.objects.get(organization=organization, name=_WORKER_ROLE_NAME)
    for legacy_pk in legacy_pks:
        result = stage_imported_account(
            organization=organization,
            role=role,
            actor=actor,
            username=f"myedu.worker.{organization.slug}.{legacy_pk}",
            email="" if legacy_pk in blank_email else f"worker{legacy_pk}@{organization.slug}.test",
        )
        _map(
            run_id,
            actor,
            entity_type=_WORKER_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=USER_MODEL_LABEL,
            target_pk=result.user.pk,
        )
        staged[legacy_pk] = result.user
    return staged


def _seeded_context(organization, actor, run, *, rows, policy=None, notes=None, cancelled=None):
    context = _context(
        plan=_plan(len(rows)),
        factory=_factory(rows),
        policy=policy or _policy(),
        organization=organization,
        actor=actor,
        notes=notes,
        cancelled=cancelled,
    )
    return replace(context, run_id=run.pk)


def _states(run):
    return dict(
        run.entity_observations.filter(entity_map__entity_type=WORKER_MATERIALISATION_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=WORKER_MATERIALISATION_ENTITY_TYPE)
    }


def _membership(organization, user):
    return Membership.objects.get(user=user, organization=organization)


# ---------------------------------------------------------------------------
# Scope yazısı + aktivasiya (V-24 / V-25 / E-11)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_activating_run_scopes_and_activates_in_one_unit_of_work(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-primary")
    rows = [_worker_row(1), _worker_row(2, department_id=6)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    units = _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2))
    notes = []

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, notes=notes))

    assert dict(report.state_counts) == {"worker_materialised": 2}
    assert _states(run) == {"1": "migrated", "2": "migrated"}
    assert dict(report.issue_counts) == {}
    assert notes == [f"{WORKER_PHASE_KEY}.records.2"]
    # Derived faza heç bir batch zəncirinə sahib deyil.
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    for legacy_pk, unit_pk in ((1, units[5].pk), (2, units[6].pk)):
        user = users[legacy_pk]
        user.refresh_from_db()
        membership = _membership(organization, user)
        profile = UserProfile.objects.get(user=user)
        # V-24: scope; V-23: rol DƏYİŞMİR; E-11: e-mail etimadı sıfırlanır.
        assert membership.scope_unit_id == unit_pk
        assert membership.role.name == _WORKER_ROLE_NAME
        assert membership.is_active is True
        assert user.is_active is True
        assert profile.access_state == UserProfile.AccessState.ACTIVE
        assert profile.email_verified is False and profile.password_change_required is True
    # MIGRATED sətir aktivləşən hesabı bağlayır (SA-2 label seam-i).
    labels = set(
        run.entity_observations.filter(
            entity_map__entity_type=WORKER_MATERIALISATION_ENTITY_TYPE, state=LegacyEntityMap.State.MIGRATED
        ).values_list("target_model_label", flat=True)
    )
    assert labels == {USER_MODEL_LABEL}


@pytest.mark.django_db
def test_a_disabled_run_writes_only_the_scope_and_defers_silently(worker_actor):
    """V-25: ``--stage-and-activate`` False — faza yalnız scope yazır."""

    actor = worker_actor
    organization = _organization(actor, "worker-disabled")
    policy = _policy(stage_and_activate=False, max_activated_accounts=0)
    rows = [_worker_row(1), _worker_row(2, department_id=6)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    units = _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert dict(report.state_counts) == {"worker_deferred": 2}
    assert "worker_materialised" not in report.state_counts
    assert dict(report.issue_counts) == {}
    assert LegacyMigrationIssue.objects.filter(run=run).count() == 0
    for legacy_pk, unit_pk in ((1, units[5].pk), (2, units[6].pk)):
        user = users[legacy_pk]
        user.refresh_from_db()
        assert user.is_active is False
        assert _membership(organization, user).scope_unit_id == unit_pk  # scope yazıldı
        assert UserProfile.objects.get(user=user).access_state == UserProfile.AccessState.STAGED


@pytest.mark.django_db
def test_a_disabled_run_never_probes_the_activation_actor(worker_actor):
    """Az-səlahiyyətli aktor heç nə aktivləşdirməyən run-u çökdürməməlidir."""

    actor = worker_actor
    organization = _organization(actor, "worker-disabled-actor")
    policy = _policy(stage_and_activate=False, max_activated_accounts=0, worker_role_name="missing-role")
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1,))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert dict(report.state_counts) == {"worker_deferred": 1}


@pytest.mark.django_db
def test_an_unstaged_worker_produces_no_map_no_issue_no_counter(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-unstaged")
    rows = [_worker_row(1), _worker_row(2)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1,))  # 2 qəsdən stage olunmur

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"worker_materialised": 1}
    assert not LegacyEntityMap.objects.filter(entity_type=WORKER_MATERIALISATION_ENTITY_TYPE, legacy_pk="2").exists()
    assert not LegacyMigrationIssue.objects.filter(run=run, legacy_pk="2").exists()


# ---------------------------------------------------------------------------
# V-24: SKIPPED + idempotent scope davranışı
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_unresolved_department_is_skipped_without_touching_anything(worker_actor):
    """V-24: OrgUnit tapılmadı — SKIPPED + WARNING, nə scope, nə aktivasiya."""

    actor = worker_actor
    organization = _organization(actor, "worker-unresolved")
    rows = [_worker_row(1, department_id=999), _worker_row(2, department_id=None)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"worker_deferred": 2}
    assert _states(run) == {"1": "skipped", "2": "skipped"}
    assert _issues(run) == {
        ("1", "legacy_worker_department_unresolved"): "warning",
        ("2", "legacy_worker_department_unresolved"): "warning",
    }
    for user in users.values():
        user.refresh_from_db()
        assert user.is_active is False
        assert _membership(organization, user).scope_unit_id is None


@pytest.mark.django_db
def test_a_preexisting_different_scope_is_never_overwritten(worker_actor):
    """V-24: mövcud fərqli ``scope_unit``-ə toxunma + INFO (idempotent replay)."""

    actor = worker_actor
    organization = _organization(actor, "worker-preexisting-scope")
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    units = _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1,))
    membership = _membership(organization, users[1])
    membership.scope_unit = units[6]  # başqa kafedra — əl ilə verilmiş qərar
    membership.save(update_fields=["scope_unit"])

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    # Sətir yenə də aktivləşir: scope qərarı toxunulmaz, INFO qeyd olunur.
    assert dict(report.state_counts) == {"worker_materialised": 1}
    assert _issues(run) == {("1", "legacy_worker_scope_preexisting"): "info"}
    membership.refresh_from_db()
    assert membership.scope_unit_id == units[6].pk


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-replay")
    rows = [_worker_row(1), _worker_row(2, department_id=6)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1, 2))
    phase = WorkerMaterialisationPhase()

    first = phase.run(_seeded_context(organization, actor, run, rows=rows))
    second = phase.run(_seeded_context(organization, actor, run, rows=rows))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=WORKER_MATERIALISATION_ENTITY_TYPE).count() == 2


# ---------------------------------------------------------------------------
# Kap davranışı (V-25): worker_deferred + ortaq büdcə
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_activation_cap_defers_every_row_beyond_it_but_still_scopes(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-capped")
    policy = _policy(max_activated_accounts=1)
    rows = [_worker_row(1), _worker_row(2, department_id=6)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    units = _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert dict(report.state_counts) == {"worker_materialised": 1, "worker_deferred": 1}
    assert _issues(run) == {("2", "legacy_worker_activation_cap_reached"): "warning"}
    users[2].refresh_from_db()
    assert users[2].is_active is False
    # Kap yalnız aktivasiyanı saxlayır — scope yenə də yazılır (V-24).
    assert _membership(organization, users[2]).scope_unit_id == units[6].pk


@pytest.mark.django_db
def test_sar_activations_consume_the_shared_cap_before_any_worker(worker_actor):
    """V-25: ``max_activated_accounts`` worker+SAR aktivasiyalarının CƏMİdir."""

    actor = worker_actor
    organization = _organization(actor, "worker-shared-cap")
    policy = _policy(max_activated_accounts=1)
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1,))
    # Bu run-un SAR fazasının artıq aktivləşdirdiyi bir tələbə — MIGRATED
    # müşahidə validatordan keçməlidir, ona görə icazəli stub veririk.
    upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type=SAR_ENTITY_TYPE,
        legacy_pk="901",
        source_row_hash=_seed_hash("sar:901"),
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label=STUDENT_RECORD_MODEL_LABEL,
        target_pk="00000000-0000-0000-0000-000000000901",
        target_validators={STUDENT_RECORD_MODEL_LABEL: lambda **_kwargs: TargetValidation(True, True)},
    )

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    # Büdcənin tək yeri SAR tərəfindən içilib: worker kapa dəyir.
    assert dict(report.state_counts) == {"worker_deferred": 1}
    assert _issues(run) == {("1", "legacy_worker_activation_cap_reached"): "warning"}
    users[1].refresh_from_db()
    assert users[1].is_active is False


@pytest.mark.django_db
def test_a_resumed_migrated_row_counts_against_the_cap(worker_actor):
    """Resume olunan aktivasiya yenə də büdcə istehlak etməlidir."""

    actor = worker_actor
    organization = _organization(actor, "worker-resume-cap")
    policy = _policy(max_activated_accounts=1)
    rows = [_worker_row(1), _worker_row(2, department_id=6)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2))
    phase = WorkerMaterialisationPhase()

    # 1-ci keçid 1-ci işçinin qərarı möhürlənən an dayandırılır.
    def cancel_after_the_first_record():
        return LegacyEntityMap.objects.filter(entity_type=WORKER_MATERIALISATION_ENTITY_TYPE, legacy_pk="1").exists()

    with pytest.raises((LegacyRehearsalInterrupted, LegacySourceExtractionError)):
        phase.run(
            _seeded_context(organization, actor, run, rows=rows, policy=policy, cancelled=cancel_after_the_first_record)
        )
    assert _states(run) == {"1": "migrated"}

    report = phase.run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert dict(report.state_counts) == {"worker_materialised": 1, "worker_deferred": 1}
    users[2].refresh_from_db()
    assert users[2].is_active is False
    assert _issues(run)[("2", "legacy_worker_activation_cap_reached")] == "warning"


# ---------------------------------------------------------------------------
# V-23 bayraqları və imtina yolu
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_administrative_and_unknown_type_flags_never_change_the_role(worker_actor):
    """V-23: rol yüksəltmə YOXDUR — yalnız INFO issue-lar."""

    actor = worker_actor
    organization = _organization(actor, "worker-flags")
    rows = [
        _worker_row(1, inzibati=1),
        _worker_row(2, department_id=6, teacher_type=9),
        _worker_row(3, teacher_type=None, inzibati=1),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1, 2, 3))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"worker_materialised": 3}
    assert _issues(run) == {
        ("1", "legacy_worker_administrative_flag"): "info",
        ("2", "legacy_worker_type_unknown"): "info",
        ("3", "legacy_worker_administrative_flag"): "info",
        ("3", "legacy_worker_type_unknown"): "info",
    }
    for user in users.values():
        assert _membership(organization, user).role.name == _WORKER_ROLE_NAME


@pytest.mark.django_db
def test_a_refused_activation_is_quarantined_and_rolls_the_scope_back(worker_actor):
    """E-10/V-27: imtina yarı-yazılmış scope da qoymur — hər şey geri qayıdır."""

    actor = worker_actor
    organization = _organization(actor, "worker-refused")
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    users = _stage_workers(organization, actor, run.pk, (1,), blank_email=(1,))

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"worker_unresolved": 1}
    assert _states(run) == {"1": "quarantined"}
    assert _issues(run) == {("1", "legacy_worker_activation_refused"): "warning"}
    users[1].refresh_from_db()
    assert users[1].is_active is False
    assert UserProfile.objects.get(user=users[1]).access_state == UserProfile.AccessState.STAGED
    # Scope yazısı EYNİ tranzaksiyada idi və onunla birlikdə geri qayıtdı.
    assert _membership(organization, users[1]).scope_unit_id is None
    observation = run.entity_observations.get(entity_map__entity_type=WORKER_MATERIALISATION_ENTITY_TYPE)
    assert observation.target_model_label == "" and observation.target_pk == ""


@pytest.mark.django_db
def test_a_missing_worker_role_is_a_config_refusal_before_any_row(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-no-role")
    policy = _policy(worker_role_name="does-not-exist")
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1,))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert exc_info.value.code == "legacy_rehearsal_worker_role_unavailable"
    assert not LegacyEntityMap.objects.filter(entity_type=WORKER_MATERIALISATION_ENTITY_TYPE).exists()


# ---------------------------------------------------------------------------
# SA-2 seam və determinizm
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_ledger_rebuild(worker_actor):
    """SA-2: MIGRATED sətirlər real ``auth.user`` label-i ilə yenidən qurulur."""

    actor = worker_actor
    organization = _organization(actor, "worker-rebuild")
    rows = [_worker_row(1), _worker_row(2, department_id=999), _worker_row(3, department_id=6)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1, 2, 3))
    phase = WorkerMaterialisationPhase()
    plan = _plan(len(rows))

    live = phase.run(_seeded_context(organization, actor, run, rows=rows))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts) == {"worker_materialised": 2, "worker_deferred": 1}
    assert (rebuilt.phase_key, rebuilt.order) == (live.phase_key, live.order)
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()
    assert rebuilt.staged_account_count == live.staged_account_count == 0
    # C5 issue saylarını həmişə ledger-dən törədir, faza keçidindən yox.
    assert dict(rebuilt.issue_counts) == {}
    assert dict(live.issue_counts) != {}


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(worker_actor):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    actor = worker_actor
    digests = []
    rows = [_worker_row(1, inzibati=1), _worker_row(2, department_id=6), _worker_row(3, department_id=999)]
    for slug in ("worker-run-a", "worker-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
        _seed_departments(organization)
        _stage_workers(organization, actor, run.pk, (1, 2, 3))
        digests.append(
            WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows)).phase_digest
        )

    assert digests[0] == digests[1]


@pytest.mark.django_db
def test_the_source_row_hash_never_leaks_a_credential_column(worker_actor):
    actor = worker_actor
    organization = _organization(actor, "worker-credentials")
    rows = [_worker_row(1)]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    _stage_workers(organization, actor, run.pk, (1,))
    factory = _factory(rows)
    context = replace(
        _context(plan=_plan(len(rows)), factory=factory, organization=organization, actor=actor),
        run_id=run.pk,
    )

    WorkerMaterialisationPhase().run(context)

    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 1  # tək qərar keçidi — ikinci kontrakt yoxdur
    assert all("password" not in statement and "pin_for_lock" not in statement for statement in statements)
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


def test_the_worker_name_is_written_from_the_source(worker_actor):
    """2026-08-28 reqressiyası: idxal edilən müəllim UI-da öz ADI ilə görünməlidir.

    Tələbə tərəfində (``student_placement``) ad yazılırdı, işçi tərəfində YOX —
    715 müəllimin hamısı ``myedu.worker.N`` kimi adsız qalırdı.  Müqavilə tələbə
    ilə eynidir: yalnız BOŞ sahə doldurulur, mövcud ad üzərinə yazılmır.
    """

    from apps.legacy_import.services.rehearsal_worker_targets import write_worker_names

    user = get_user_model().objects.create_user(username="myedu.worker.name.1", email="", password=None)

    assert write_worker_names(str(user.pk), "Elvin", "Qurbanov") == "written"
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Elvin", "Qurbanov")

    # Təkrar çağırış mövcud adı QORUYUR (idempotent, üzərinə yazmır).
    assert write_worker_names(str(user.pk), "Başqa", "Ad") == "preserved"
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Elvin", "Qurbanov")

    # Mənbədə ad yoxdursa heç nə yazılmır.
    blank = get_user_model().objects.create_user(username="myedu.worker.name.2", email="", password=None)
    assert write_worker_names(str(blank.pk), "", "") == "blank"


@pytest.mark.django_db
def test_the_worker_patronymic_is_written_from_the_source(worker_actor):
    """2026-08-28 tapıntısı (B-1): 8 441 profildən heç birində ata adı yox idi.

    RİM axtarışı hesabı ad+soyad+ATA ADI üçlüyü ilə tapır, ona görə boş
    ``patronymic`` real datada «ata adı ilə tap» tələbini tamamilə sındırır.
    Müqavilə ad/soyadla eynidir: yalnız BOŞ sahə doldurulur.
    """

    from types import SimpleNamespace

    from apps.legacy_import.services.rehearsal_worker_targets import write_worker_patronymic

    actor = worker_actor
    organization = _organization(actor, "worker-patronymic")
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(1))
    user = _stage_workers(organization, actor, run.pk, (1,))[1]
    context = SimpleNamespace(organization=organization)

    assert write_worker_patronymic(context, user_pk=str(user.pk), patronymic="Şahin") == "written"
    assert UserProfile.objects.get(user=user).patronymic == "Şahin"

    # Təkrar çağırış mövcud dəyəri QORUYUR (idempotent, üzərinə yazmır).
    assert write_worker_patronymic(context, user_pk=str(user.pk), patronymic="Başqa") == "preserved"
    assert UserProfile.objects.get(user=user).patronymic == "Şahin"

    # Mənbədə ata adı yoxdursa heç nə yazılmır (hədəf sorğusu belə atılmır).
    other = _stage_workers(organization, actor, run.pk, (2,))[2]
    assert write_worker_patronymic(context, user_pk=str(other.pk), patronymic="") == "blank"
    assert UserProfile.objects.get(user=other).patronymic == ""


@pytest.mark.django_db
def test_an_activating_run_writes_every_identity_field(worker_actor):
    """Reqressiya: aktivasiya yolunda ad/soyad/ata adı SƏSSİZCƏ itirdi.

    ``_decide`` aktivasiya pilləsində ``WorkerRequest``-i sıfırdan qururdu və
    ``first_name``/``last_name`` default boşa düşürdü — yəni real
    ``--stage-and-activate`` qaçışında (prod köçürməsi) 715 müəllim yenə adsız
    qalırdı, halbuki «disabled» qaçışında ad yazılırdı.
    """

    actor = worker_actor
    organization = _organization(actor, "worker-identity")
    rows = [_worker_row(1, first_name="Elvin", last_name="Qurbanov", father_name="C&uuml;c&uuml;")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_departments(organization)
    user = _stage_workers(organization, actor, run.pk, (1,))[1]

    report = WorkerMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"worker_materialised": 1}
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Elvin", "Qurbanov")
    # HTML entity mənbədə xam qalıb; ``clean_text`` onu hədəfə yazmazdan əvvəl açır.
    assert UserProfile.objects.get(user=user).patronymic == "Cücü"
