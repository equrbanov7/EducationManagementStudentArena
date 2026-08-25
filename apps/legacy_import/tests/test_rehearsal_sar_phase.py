"""Phase ``sar_materialisation`` tests: §5.5 matrix, §5.6 ladder, digest seam."""

import hashlib
from dataclasses import replace

import pytest

from apps.accounts.models import UserProfile
from apps.accounts.public import stage_imported_account
from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services import rehearsal_sar_targets
from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    STUDENT_STATUS_FIELDS,
    is_credential_field,
)
from apps.legacy_import.services.ledger import create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    CURRICULUM_MODEL_LABEL,
    ORG_UNIT_MODEL_LABEL,
    STUDENT_RECORD_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_catalog_phase import CURRICULUM_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    PlanSemesterScheme,
    RehearsalContext,
    RehearsalPolicy,
    SarCurriculumFallback,
    StudentIdentifierPolicy,
    UsernamePolicy,
    encoded_part,
)
from apps.legacy_import.services.rehearsal_placement_phase import PLACEMENT_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.rehearsal_sar_phase import (
    DERIVED_DIGEST_NAMESPACE,
    SAR_PHASE_KEY,
    SarMaterialisationPhase,
)
from apps.legacy_import.services.rehearsal_sar_targets import (
    ACTIVATION_REASON_CODE,
    ISSUE_SEVERITY,
    SAR_ENTITY_TYPE,
    activation_evidence_digest,
    sar_derivation_hash,
)
from apps.legacy_import.services.rehearsal_structure_phase import GROUP_ENTITY_TYPE
from apps.legacy_import.services.source_extraction import (
    _AUDITED_CONTRACTS,
    LegacyDiscoveredTable,
    LegacySourceExtractionError,
)
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType

_SNAPSHOT_SHA256 = None  # filled from the canonical plan below
_STUDENT_ENTITY_TYPE = "student"
_STUDENT_ROLE_NAME = "student"
_PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "sar_materialisation",
)
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "show_password", "pin_for_lock")
# ``students`` is projected through TWO contracts here (identity + V-18 status),
# so the discovered column list is their de-duplicated union.
_SOURCE_COLUMNS = tuple(
    dict.fromkeys(
        (
            *STUDENT_IDENTITY_FIELDS.allowed_fields,
            *STUDENT_STATUS_FIELDS.allowed_fields,
            *_CREDENTIAL_COLUMNS,
        )
    )
)


# ---------------------------------------------------------------------------
# Fake source (same shape as the identity/structure/placement fixtures)
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


def _student_row(legacy_pk, **overrides):
    values = {field_name: None for field_name in _SOURCE_COLUMNS}
    values["id"] = legacy_pk
    values["azadedildi"] = 0
    values["password"] = "hunter2-raw-credential"
    values.update(overrides)
    return values


def _plan(students):
    from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=students,
        entries=(replace(canonical.entry_for("students"), expected_rows=students),),
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
        "student_role_name": _STUDENT_ROLE_NAME,
        "worker_role_name": "worker",
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
    phase = SarMaterialisationPhase()

    assert phase.phase_key == SAR_PHASE_KEY and phase.order == 28
    assert phase.source_tables == () and phase.entity_types == (SAR_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(3)) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "sar_created"
    assert phase.derived_state_key("skipped") == "sar_deferred"
    assert phase.derived_state_key("quarantined") == "sar_unresolved"


def test_issue_severity_map_covers_exactly_the_sar_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_sar_admission_year_missing": "warning",
        "legacy_sar_activation_cap_reached": "warning",
        "legacy_sar_activation_refused": "warning",
        "legacy_sar_curriculum_program_conflict": "warning",
        "legacy_sar_curriculum_unmapped": "warning",
        "legacy_sar_curriculum_substituted": "warning",
        "legacy_sar_curriculum_synthesised": "warning",
        "legacy_sar_write_refused": "warning",
        "legacy_sar_departed_student": "info",
        "legacy_sar_group_missing": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    # §6.2's uniqueness rule: ``LegacyMigrationIssue`` is unique on
    # (run, source_table="students", legacy_pk, rule_code) across BOTH phases.
    assert all(rule_code.startswith("legacy_sar_") for rule_code in ISSUE_SEVERITY)


def test_the_v18_status_contract_is_audited_and_credential_free():
    """V-18(a): a second, deliberately tiny ``students`` projection."""

    assert STUDENT_STATUS_FIELDS.source_table == "students"
    assert STUDENT_STATUS_FIELDS.version == "status-v1"
    assert STUDENT_STATUS_FIELDS.allowed_fields == ("id", "azadedildi")
    assert not any(is_credential_field(field_name) for field_name in STUDENT_STATUS_FIELDS.allowed_fields)
    # Widening ``STUDENT_IDENTITY_FIELDS`` instead would have changed its
    # fingerprint and therefore every identity ``source_row_hash`` ever recorded.
    assert STUDENT_STATUS_FIELDS.fingerprint != STUDENT_IDENTITY_FIELDS.fingerprint
    assert _AUDITED_CONTRACTS[STUDENT_STATUS_FIELDS.fingerprint] == STUDENT_STATUS_FIELDS


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        SarMaterialisationPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [
        ("sar_materialisation",),
        ("identity_cohort", "student_placement", "sar_materialisation"),
        ("academic_structure", "identity_cohort", "student_placement", "sar_materialisation"),
    ],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    context = _context(plan=_plan(0), factory=_factory([]), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        SarMaterialisationPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_a_cancellation_request_stops_the_phase_before_it_reads_anything():
    factory = _factory([_student_row(1)])
    context = _context(plan=_plan(1), factory=factory, cancelled=lambda: True)

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        SarMaterialisationPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert factory.connections == []


def test_the_activation_evidence_digest_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-activation-evidence-v1\x00")
    for part in ("rehearsal-identity-v1.abcdef012345", "a" * 64, "student", "17"):
        digest.update(encoded_part(part))

    assert (
        activation_evidence_digest(
            transform_version="rehearsal-identity-v1.abcdef012345",
            snapshot_sha256="a" * 64,
            legacy_pk=17,
        )
        == digest.hexdigest()
    )
    assert ACTIVATION_REASON_CODE == "signed_authoritative_export"


def test_the_sar_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-sar-derivation-v1\x00")
    for part in (
        STUDENT_IDENTITY_FIELDS.fingerprint,
        "1",
        "b" * 64,
        "created",
        "050620",
        "myedu-grp-20",
        "2019",
        "legacy",
        "050620:2019",
        "activated",
    ):
        digest.update(encoded_part(part))

    computed = sar_derivation_hash(
        legacy_pk=1,
        placement_row_hash="b" * 64,
        outcome_token="created",
        program_code="050620",
        group_slug="myedu-grp-20",
        admission_year_text="2019",
        curriculum_source="legacy",
        curriculum_key="050620:2019",
        activation_state="activated",
    )

    assert computed == digest.hexdigest()
    # The activation decision is part of the identity: a row activated by one
    # run and adopted by another must NOT hash the same.
    assert computed != sar_derivation_hash(
        legacy_pk=1,
        placement_row_hash="b" * 64,
        outcome_token="created",
        program_code="050620",
        group_slug="myedu-grp-20",
        admission_year_text="2019",
        curriculum_source="legacy",
        curriculum_key="050620:2019",
        activation_state="preexisting",
    )


# ---------------------------------------------------------------------------
# Ledger-backed environment
# ---------------------------------------------------------------------------


@pytest.fixture()
def sar_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="sar_phase_actor",
        email="sar-phase-actor@example.test",
        password="test-only",
    )


def _organization(actor, slug):
    organization = Organization.objects.create(
        name=f"SAR {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    # The organization factory already seeds the default role set; the phase
    # only ever resolves it by ``policy.student_role_name``.
    Role.objects.get_or_create(
        organization=organization,
        name=_STUDENT_ROLE_NAME,
        defaults={"display_name": "Tələbə", "level": 10, "permissions": [], "is_active": True},
    )
    Role.objects.filter(organization=organization, name=_STUDENT_ROLE_NAME).update(is_active=True)
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


# (legacy_pk, degree_level, admission_year, curricula_id)
_SEEDED_GROUPS = (
    (20, "bachelor", 2019, 100),  # M1: the plan really belongs to this program
    (21, "bachelor", 2019, 0),  # M4: the group names no plan at all
    (22, "bachelor", 2019, 300),  # M3: the plan is not mapped by this run
    (23, "bachelor", 2019, 200),  # M2: the plan belongs to the master program
    (24, "master", None, 0),  # M5 vehicle: no admission year anywhere
)


def _seed_structure(organization, actor, run_id):
    """Everything ``academic_structure`` and ``academic_catalog`` leave behind."""

    speciality = OrgUnit.objects.create(
        organization=organization,
        slug="myedu-spec-10",
        unit_type=OrgUnitType.SPECIALTY,
        name="İxtisas A",
        code="050620",
        settings={"legacy": {"table": "speciality", "id": 10}},
    )
    programs = {}
    for code, degree, ects in (("050620", "bachelor", 240), ("050620-M", "master", 120)):
        programs[degree] = Program.objects.create(
            organization=organization,
            specialty_unit=speciality,
            code=code,
            name="İxtisas A",
            degree_level=degree,
            ects_total=ects,
        )
    for legacy_pk, degree, year, curricula_id in _SEEDED_GROUPS:
        unit = OrgUnit.objects.create(
            organization=organization,
            slug=f"myedu-grp-{legacy_pk}",
            unit_type=OrgUnitType.GROUP,
            name=f"Qrup {legacy_pk}",
            parent=speciality,
            settings={
                "education_form": "full_time",
                "admission_year": year,
                "sector": "az",
                "degree_level": degree,
                "legacy": {"table": "groups", "id": legacy_pk, "curricula_id": curricula_id},
            },
        )
        _map(
            run_id,
            actor,
            entity_type=GROUP_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=ORG_UNIT_MODEL_LABEL,
            target_pk=unit.pk,
        )
    # The catalogue phase's output: legacy plan 100 → the bachelor programme's
    # 2019 plan, legacy plan 200 → the MASTER programme's 2019 plan (M2).
    for legacy_pk, degree in ((100, "bachelor"), (200, "master")):
        curriculum = Curriculum.objects.create(
            organization=organization, program=programs[degree], admission_year=2019, name="", is_active=True
        )
        _map(
            run_id,
            actor,
            entity_type=CURRICULUM_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=CURRICULUM_MODEL_LABEL,
            target_pk=curriculum.pk,
        )
    return programs


def _stage_students(organization, actor, run_id, legacy_pks, *, blank_email=()):
    staged = {}
    role = Role.objects.get(organization=organization, name=_STUDENT_ROLE_NAME)
    for legacy_pk in legacy_pks:
        result = stage_imported_account(
            organization=organization,
            role=role,
            actor=actor,
            username=f"myedu.student.{organization.slug}.{legacy_pk}",
            email="" if legacy_pk in blank_email else f"student{legacy_pk}@{organization.slug}.test",
            student_identifier=str(legacy_pk),
        )
        _map(
            run_id,
            actor,
            entity_type=_STUDENT_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            label=USER_MODEL_LABEL,
            target_pk=result.user.pk,
        )
        staged[legacy_pk] = result.user
    return staged


# legacy_pk → (group_id, entry_year); 8 is deliberately never staged.
_COHORT = (
    (1, 20, "2019"),  # M1 — bind the legacy curriculum
    (2, 21, "2019"),  # M4 — no plan named ⇒ fallback substitutes the 2019 row
    (3, 22, "2020"),  # M3 — unmapped plan ⇒ fallback synthesises a 2020 row
    (4, 23, "2019"),  # M2 — plan belongs to another program
    (5, 24, ""),  # M5 — no admission year in ANY source
    (6, 999, "2019"),  # M6 — the placement itself is quarantined
    (7, 20, "2019"),  # V-18 — released student
    (8, 20, "2019"),  # never staged: no map, no issue, no counter
)
_STAGED_PKS = (1, 2, 3, 4, 5, 6, 7)


def _cohort_rows():
    return [
        _student_row(legacy_pk, group_id=group_id, entry_year=entry_year, azadedildi=1 if legacy_pk == 7 else 0)
        for legacy_pk, group_id, entry_year in _COHORT
    ]


def _seed_placements(organization, actor, run_id):
    """What ``student_placement`` sealed: SKIPPED unless the group is dangling."""

    for legacy_pk, group_id, _entry_year in _COHORT[:-1]:
        _map(
            run_id,
            actor,
            entity_type=PLACEMENT_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            state=(LegacyEntityMap.State.QUARANTINED if group_id == 999 else LegacyEntityMap.State.SKIPPED),
        )


def _seeded_context(organization, actor, run, *, rows=None, policy=None, notes=None, cancelled=None):
    source_rows = _cohort_rows() if rows is None else rows
    context = _context(
        plan=_plan(len(source_rows)),
        factory=_factory(source_rows),
        policy=policy or _policy(),
        organization=organization,
        actor=actor,
        notes=notes,
        cancelled=cancelled,
    )
    return replace(context, run_id=run.pk)


@pytest.fixture()
def seeded(sar_actor):
    actor = sar_actor
    organization = _organization(actor, "sar-primary")
    plan = _plan(len(_COHORT))
    run = _running_run(organization, actor, policy=_policy(), plan=plan)
    programs = _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, _STAGED_PKS)
    _seed_placements(organization, actor, run.pk)
    return organization, actor, run, users, programs


def _states(run):
    return dict(
        LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type=SAR_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=SAR_ENTITY_TYPE)
    }


# ---------------------------------------------------------------------------
# The disabled default: the first slice-2 rehearsal touches NO account
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_disabled_run_defers_every_row_without_writing_anything(sar_actor):
    """§5.6: ``stage_and_activate=False`` is silent by design."""

    actor = sar_actor
    organization = _organization(actor, "sar-disabled")
    policy = _policy(stage_and_activate=False, max_activated_accounts=0)
    rows = [_student_row(legacy_pk, group_id=20, entry_year="2019") for legacy_pk in (1, 2)]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, (1, 2))
    for legacy_pk in (1, 2):
        _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=legacy_pk, state=LegacyEntityMap.State.SKIPPED)
    notes = []

    report = SarMaterialisationPhase().run(
        _seeded_context(organization, actor, run, rows=rows, policy=policy, notes=notes)
    )

    assert dict(report.state_counts) == {"sar_deferred": 2}
    assert "sar_created" not in report.state_counts
    assert dict(report.issue_counts) == {}
    assert LegacyMigrationIssue.objects.filter(run=run).count() == 0
    assert StudentAcademicRecord.objects.count() == 0
    assert all(not user.__class__.objects.get(pk=user.pk).is_active for user in users.values())
    assert notes == [f"{SAR_PHASE_KEY}.records.2"]
    # A derived phase owns no batch chain at all.
    assert LegacyImportBatch.objects.filter(run=run).count() == 0


@pytest.mark.django_db
def test_a_disabled_run_never_probes_the_activation_actor(sar_actor, django_user_model):
    """An under-privileged actor must not fail a run that activates nothing."""

    actor = sar_actor
    organization = _organization(actor, "sar-disabled-actor")
    policy = _policy(stage_and_activate=False, max_activated_accounts=0, student_role_name="missing-role")
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    _stage_students(organization, actor, run.pk, (1,))
    _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert dict(report.state_counts) == {"sar_deferred": 1}


# ---------------------------------------------------------------------------
# The §5.5 matrix and the §5.6 ladder
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_full_curriculum_matrix_and_activation_ladder(seeded):
    organization, actor, run, users, programs = seeded

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    assert _states(run) == {
        "1": "migrated",  # M1
        "2": "migrated",  # M4 ⇒ substituted
        "3": "migrated",  # M3 ⇒ synthesised
        "4": "migrated",  # M2 ⇒ substituted under ``synthesise``
        "5": "skipped",  # M5
        "6": "skipped",  # M6
        "7": "skipped",  # V-18 departed
    }
    assert dict(report.state_counts) == {"sar_created": 4, "sar_deferred": 3}
    assert _issues(run) == {
        ("2", "legacy_sar_curriculum_unmapped"): "warning",
        ("2", "legacy_sar_curriculum_substituted"): "warning",
        ("3", "legacy_sar_curriculum_unmapped"): "warning",
        ("3", "legacy_sar_curriculum_synthesised"): "warning",
        ("4", "legacy_sar_curriculum_program_conflict"): "warning",
        ("4", "legacy_sar_curriculum_substituted"): "warning",
        ("5", "legacy_sar_admission_year_missing"): "warning",
        ("7", "legacy_sar_departed_student"): "info",
    }
    # M1 binds the LEGACY curriculum; the fallbacks converge on the same row.
    bachelor_2019 = Curriculum.objects.get(organization=organization, program=programs["bachelor"], admission_year=2019)
    records = {
        record.student_id: record
        for record in StudentAcademicRecord.objects.filter(organization=organization).select_related("curriculum")
    }
    assert len(records) == 4
    assert records[users[1].pk].curriculum_id == bachelor_2019.pk
    assert records[users[2].pk].curriculum_id == bachelor_2019.pk
    assert records[users[4].pk].curriculum_id == bachelor_2019.pk
    assert records[users[3].pk].curriculum.admission_year == 2020
    assert all(record.program_id == programs["bachelor"].pk for record in records.values())
    assert all(record.status == "enrolled" and record.is_active for record in records.values())


@pytest.mark.django_db
def test_a_deferred_row_never_activates_its_account(seeded):
    organization, actor, run, users, _programs = seeded

    SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    for legacy_pk in (5, 6, 7):
        user = users[legacy_pk]
        user.refresh_from_db()
        assert user.is_active is False
        assert UserProfile.objects.get(user=user).access_state == UserProfile.AccessState.STAGED


@pytest.mark.django_db
def test_activation_neutralises_the_legacy_email_in_the_same_unit_of_work(seeded):
    """E-11: activation asserts existence, never that the address is verified."""

    organization, actor, run, users, _programs = seeded

    SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    user = users[1]
    user.refresh_from_db()
    profile = UserProfile.objects.get(user=user)
    assert user.is_active is True
    assert profile.access_state == UserProfile.AccessState.ACTIVE
    assert profile.email_verified is False and profile.password_change_required is True
    assert Membership.objects.get(user=user, organization=organization).is_active is True


@pytest.mark.django_db
def test_an_unstaged_student_produces_no_map_no_issue_no_counter(seeded):
    organization, actor, run, _users, _programs = seeded

    SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    assert not LegacyEntityMap.objects.filter(entity_type=SAR_ENTITY_TYPE, legacy_pk="8").exists()
    assert not LegacyMigrationIssue.objects.filter(run=run, legacy_pk="8").exists()


@pytest.mark.django_db
def test_strict_refuses_every_row_without_a_coherent_legacy_curriculum(sar_actor):
    """§5.5: ``strict`` means no legacy plan ⇒ no student record at all."""

    actor = sar_actor
    organization = _organization(actor, "sar-strict")
    policy = _policy(sar_curriculum_fallback=SarCurriculumFallback.STRICT)
    rows = _cohort_rows()
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    _stage_students(organization, actor, run.pk, _STAGED_PKS)
    _seed_placements(organization, actor, run.pk)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, policy=policy))

    assert _states(run) == {
        "1": "migrated",  # M1 is the only coherent binding
        "2": "skipped",
        "3": "skipped",
        "4": "skipped",
        "5": "skipped",
        "6": "skipped",
        "7": "skipped",
    }
    assert dict(report.state_counts) == {"sar_created": 1, "sar_deferred": 6}
    assert StudentAcademicRecord.objects.count() == 1
    # No curriculum was minted: ``strict`` writes nothing it cannot justify.
    assert Curriculum.objects.filter(organization=organization).count() == 2
    assert _issues(run)[("4", "legacy_sar_curriculum_program_conflict")] == "warning"


@pytest.mark.django_db
def test_a_synthetic_curriculum_converges_onto_the_legacy_one(seeded):
    """``uniq_curriculum_program_year`` IS the lookup key, so nothing duplicates."""

    organization, actor, run, _users, programs = seeded
    before = Curriculum.objects.filter(organization=organization).count()

    SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    # Exactly ONE new row: the 2020 plan student 3 needed; the three 2019
    # bachelor students all landed on the curriculum the catalogue phase wrote.
    assert Curriculum.objects.filter(organization=organization).count() == before + 1
    assert (
        Curriculum.objects.filter(organization=organization, program=programs["bachelor"], admission_year=2019).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Cap, resume and refusal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_activation_cap_defers_every_row_beyond_it(sar_actor):
    actor = sar_actor
    organization = _organization(actor, "sar-capped")
    policy = _policy(max_activated_accounts=2)
    rows = _cohort_rows()
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    _stage_students(organization, actor, run.pk, _STAGED_PKS)
    _seed_placements(organization, actor, run.pk)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, policy=policy))

    assert dict(report.state_counts) == {"sar_created": 2, "sar_deferred": 5}
    assert StudentAcademicRecord.objects.count() == 2
    assert _issues(run)[("3", "legacy_sar_activation_cap_reached")] == "warning"
    assert _issues(run)[("4", "legacy_sar_activation_cap_reached")] == "warning"


@pytest.mark.django_db
def test_a_resumed_migrated_row_counts_against_the_cap(sar_actor):
    """The 2026-08-26 finding: a replayed activation must still consume budget."""

    actor = sar_actor
    organization = _organization(actor, "sar-resume-cap")
    policy = _policy(max_activated_accounts=1)
    rows = _cohort_rows()
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, _STAGED_PKS)
    _seed_placements(organization, actor, run.pk)
    phase = SarMaterialisationPhase()

    # Pass 1 is interrupted the moment student 1's decision is sealed.
    def cancel_after_the_first_record():
        return LegacyEntityMap.objects.filter(entity_type=SAR_ENTITY_TYPE, legacy_pk="1").exists()

    with pytest.raises((LegacyRehearsalInterrupted, LegacySourceExtractionError)):
        phase.run(_seeded_context(organization, actor, run, policy=policy, cancelled=cancel_after_the_first_record))
    assert _states(run) == {"1": "migrated"}

    report = phase.run(_seeded_context(organization, actor, run, policy=policy))

    # Student 1 replays as MIGRATED and consumes the single activation slot, so
    # student 2 is capped instead of being activated a second time over budget.
    assert dict(report.state_counts) == {"sar_created": 1, "sar_deferred": 6}
    assert StudentAcademicRecord.objects.count() == 1
    users[2].refresh_from_db()
    assert users[2].is_active is False
    assert _issues(run)[("2", "legacy_sar_activation_cap_reached")] == "warning"


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(seeded):
    organization, actor, run, _users, _programs = seeded
    phase = SarMaterialisationPhase()

    first = phase.run(_seeded_context(organization, actor, run))
    second = phase.run(_seeded_context(organization, actor, run))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=SAR_ENTITY_TYPE).count() == 7
    assert StudentAcademicRecord.objects.count() == 4


@pytest.mark.django_db
def test_a_refused_activation_is_quarantined_and_rolls_everything_back(sar_actor):
    """V-11's precondition: a blank e-mail can never be activated."""

    actor = sar_actor
    organization = _organization(actor, "sar-refused")
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, (1,), blank_email=(1,))
    _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"sar_unresolved": 1}
    assert _states(run) == {"1": "quarantined"}
    assert _issues(run) == {("1", "legacy_sar_activation_refused"): "warning"}
    assert StudentAcademicRecord.objects.count() == 0
    users[1].refresh_from_db()
    assert users[1].is_active is False
    assert UserProfile.objects.get(user=users[1]).access_state == UserProfile.AccessState.STAGED
    observation = LegacyEntityObservation.objects.get(run=run, entity_map__entity_type=SAR_ENTITY_TYPE)
    assert observation.target_model_label == "" and observation.target_pk == ""


@pytest.mark.django_db
def test_a_refused_sar_write_rolls_the_activation_back(sar_actor, monkeypatch):
    """The atomic block is the whole unit of work, activation included (§8)."""

    actor = sar_actor
    organization = _organization(actor, "sar-write-refused")
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, (1,))
    _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    def refuse(*_args, **_kwargs):
        from django.db import IntegrityError

        raise IntegrityError("registrar_guard_student_record_coherence")

    monkeypatch.setattr(rehearsal_sar_targets, "_ensure_record", refuse)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"sar_unresolved": 1}
    assert _issues(run) == {("1", "legacy_sar_write_refused"): "warning"}
    assert StudentAcademicRecord.objects.count() == 0
    # The activation that DID succeed inside the block was rolled back with it.
    users[1].refresh_from_db()
    assert users[1].is_active is False
    assert UserProfile.objects.get(user=users[1]).access_state == UserProfile.AccessState.STAGED


@pytest.mark.django_db
def test_an_already_active_account_is_adopted_without_reactivation(sar_actor, django_user_model):
    """§5.6: ``preexisting`` still produces a SAR, and still consumes the cap.

    This can't be built by staging an account and then flipping its profile
    toward ``active`` with a direct ORM ``update``: on PostgreSQL, the
    ``accounts_reject_active_staged_profile`` trigger refuses exactly that
    write (a STAGED profile may only leave that state through the activation
    service), raising ``accounts_staged_activation_service_required`` — a
    trigger sqlite doesn't have, which is why this only ever failed there.
    The "already active" fixture is instead built from scratch as a NORMAL
    account (``is_active=True`` from creation, never STAGED) with its own
    active membership, mirroring the pattern already used above in
    ``test_an_actor_without_member_edit_is_refused_before_any_row``.
    """

    actor = sar_actor
    organization = _organization(actor, "sar-preexisting")
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)

    role = Role.objects.get(organization=organization, name=_STUDENT_ROLE_NAME)
    student = django_user_model.objects.create_user(
        username=f"myedu.student.{organization.slug}.1",
        email=f"student1@{organization.slug}.test",
        is_active=True,
    )
    # The profile-creation signal already defaults ``access_state`` to ACTIVE;
    # it just doesn't know which organization owns the account yet.
    UserProfile.objects.filter(user=student).update(organization=organization)
    Membership.objects.create(
        user=student,
        organization=organization,
        role=role,
        assigned_by=actor,
        is_primary=True,
        is_active=True,
    )
    users = {1: student}
    _map(
        run.pk,
        actor,
        entity_type=_STUDENT_ENTITY_TYPE,
        legacy_pk=1,
        label=USER_MODEL_LABEL,
        target_pk=student.pk,
    )

    _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"sar_created": 1}
    assert StudentAcademicRecord.objects.count() == 1
    # No activation evidence was minted: the account was already active.
    profile = UserProfile.objects.get(user=users[1])
    assert profile.email_verified is False and profile.password_change_required is False


# ---------------------------------------------------------------------------
# Pre-flights and index ambiguity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_missing_student_role_is_a_config_refusal_before_any_row(sar_actor):
    actor = sar_actor
    organization = _organization(actor, "sar-no-role")
    policy = _policy(student_role_name="does-not-exist")
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, actor, policy=policy, plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    _stage_students(organization, actor, run.pk, (1,))
    _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows, policy=policy))

    assert exc_info.value.code == "legacy_rehearsal_sar_role_unavailable"
    assert not LegacyEntityMap.objects.filter(entity_type=SAR_ENTITY_TYPE).exists()


@pytest.mark.django_db
def test_an_actor_without_member_edit_is_refused_before_any_row(sar_actor, django_user_model):
    """C-4: the ledger gate is ``member.invite``; activation needs ``member.edit``."""

    owner = sar_actor
    organization = _organization(owner, "sar-weak-actor")
    weak = django_user_model.objects.create_user(username="weak_actor", email="weak@example.test", is_active=True)
    role = Role.objects.create(
        organization=organization,
        name="importer",
        display_name="Importer",
        level=20,
        permissions=["member.invite"],
        is_active=True,
    )
    Membership.objects.create(user=weak, organization=organization, role=role, is_primary=True, is_active=True)
    UserProfile.objects.filter(user=weak).update(organization=organization)
    rows = [_student_row(1, group_id=20, entry_year="2019")]
    run = _running_run(organization, owner, policy=_policy(), plan=_plan(len(rows)))
    _seed_structure(organization, owner, run.pk)
    _stage_students(organization, owner, run.pk, (1,))
    _map(run.pk, owner, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=1, state=LegacyEntityMap.State.SKIPPED)

    context = replace(_seeded_context(organization, owner, run, rows=rows), actor=weak)
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        SarMaterialisationPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_activation_actor_unauthorized"


# ---------------------------------------------------------------------------
# The SA-2 seam: a derived phase with a NON-EMPTY target label
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_ledger_rebuild(seeded):
    """SA-2, this time with MIGRATED rows carrying a real target label."""

    organization, actor, run, _users, _programs = seeded
    phase = SarMaterialisationPhase()
    plan = _plan(len(_COHORT))

    live = phase.run(_seeded_context(organization, actor, run))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
    assert (rebuilt.phase_key, rebuilt.order) == (live.phase_key, live.order)
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()
    assert rebuilt.staged_account_count == live.staged_account_count == 0
    # C5 always re-derives issue counts from the ledger, never from a phase pass.
    assert dict(rebuilt.issue_counts) == {}
    assert dict(live.issue_counts) != {}
    labels = set(
        LegacyEntityObservation.objects.filter(
            run=run, entity_map__entity_type=SAR_ENTITY_TYPE, state=LegacyEntityMap.State.MIGRATED
        ).values_list("target_model_label", flat=True)
    )
    assert labels == {STUDENT_RECORD_MODEL_LABEL}


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(sar_actor):
    """Cross-run determinism: no UUID and no target identity enters the chain."""

    actor = sar_actor
    digests = []
    for slug in ("sar-run-a", "sar-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(_COHORT)))
        _seed_structure(organization, actor, run.pk)
        _stage_students(organization, actor, run.pk, _STAGED_PKS)
        _seed_placements(organization, actor, run.pk)
        digests.append(SarMaterialisationPhase().run(_seeded_context(organization, actor, run)).phase_digest)

    assert digests[0] == digests[1]


@pytest.mark.django_db
def test_two_legacy_plans_pointing_at_one_curriculum_are_not_ambiguous(seeded):
    """§5.1's merge rule: many legacy plans MAY share one ``Curriculum``."""

    organization, actor, run, _users, programs = seeded
    shared = Curriculum.objects.get(organization=organization, program=programs["bachelor"], admission_year=2019)
    _map(
        run.pk,
        actor,
        entity_type=CURRICULUM_ENTITY_TYPE,
        legacy_pk=102,
        label=CURRICULUM_MODEL_LABEL,
        target_pk=shared.pk,
    )

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run))

    assert dict(report.state_counts) == {"sar_created": 4, "sar_deferred": 3}


@pytest.mark.django_db
def test_the_source_row_hash_never_leaks_a_credential_column(seeded):
    organization, actor, run, _users, _programs = seeded
    factory = _factory(_cohort_rows())
    context = replace(
        _context(
            plan=_plan(len(_COHORT)),
            factory=factory,
            organization=organization,
            actor=actor,
        ),
        run_id=run.pk,
    )

    SarMaterialisationPhase().run(context)

    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 2  # one release-flag pass, one decision pass
    assert all("password" not in statement for statement in statements)
    assert all("azadedildi" in statement for statement in statements[:1])
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


@pytest.mark.django_db
def test_a_departed_student_is_blocked_whatever_the_policy_says(sar_actor):
    """V-18(b): ``azadedildi`` is a source fact, not an activation policy knob."""

    actor = sar_actor
    organization = _organization(actor, "sar-departed")
    rows = [
        _student_row(1, group_id=20, entry_year="2019", azadedildi=1),
        _student_row(2, group_id=20, entry_year="2019", azadedildi=0),
    ]
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(len(rows)))
    _seed_structure(organization, actor, run.pk)
    users = _stage_students(organization, actor, run.pk, (1, 2))
    for legacy_pk in (1, 2):
        _map(run.pk, actor, entity_type=PLACEMENT_ENTITY_TYPE, legacy_pk=legacy_pk, state=LegacyEntityMap.State.SKIPPED)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, rows=rows))

    assert dict(report.state_counts) == {"sar_created": 1, "sar_deferred": 1}
    assert _issues(run) == {("1", "legacy_sar_departed_student"): "info"}
    users[1].refresh_from_db()
    assert users[1].is_active is False
    assert StudentAcademicRecord.objects.filter(student=users[1]).count() == 0
    assert StudentAcademicRecord.objects.filter(student=users[2]).count() == 1


@pytest.mark.django_db
def test_the_semester_scheme_is_not_part_of_the_sar_decision(seeded):
    """A sanity guard: the SAR phase reads plans, never their semester tokens."""

    organization, actor, run, _users, _programs = seeded
    policy = _policy(plan_semester_scheme=PlanSemesterScheme.TERM_PAIR)

    report = SarMaterialisationPhase().run(_seeded_context(organization, actor, run, policy=policy))

    assert dict(report.state_counts) == {"sar_created": 4, "sar_deferred": 3}
