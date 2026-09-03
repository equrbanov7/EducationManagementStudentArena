"""Phase ``academic_structure`` tests: cohort, derivation, targets and batches."""

from dataclasses import replace

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services import rehearsal_structure_source as source_module
from apps.legacy_import.services.field_contracts import (
    DEPARTMENT_STRUCTURE_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
)
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from apps.legacy_import.services.rehearsal_authorizer import (
    ORG_UNIT_MODEL_LABEL,
    PROGRAM_MODEL_LABEL,
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
)
from apps.legacy_import.services.rehearsal_structure_phase import (
    ISSUE_SEVERITY,
    AcademicStructurePhase,
    ordered_departments,
)
from apps.legacy_import.services.rehearsal_structure_source import build_structure_cohort
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable, LegacySourceExtractionCancelled
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import Organization, OrgUnit
from apps.registrar.models import Program
from core.constants import OrganizationType, OrgUnitType

_SNAPSHOT_SHA256 = load_legacy_table_plan().source_snapshot_sha256
_CONTRACTS = {
    "departments": DEPARTMENT_STRUCTURE_FIELDS,
    "speciality": SPECIALITY_STRUCTURE_FIELDS,
    "groups": GROUP_STRUCTURE_FIELDS,
}
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "show_password", "pin_for_lock")


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
        return _FakeCursor(
            tuple((field_name, None, None, None, None, None, None) for field_name in field_names),
            [tuple(row[field_name] for field_name in field_names) for row in rows],
        )

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


def _row(contract, legacy_pk, **overrides):
    values = {field_name: None for field_name in contract.allowed_fields}
    values["id"] = legacy_pk
    values["password"] = "hunter2-raw-credential"
    values.update(overrides)
    return values


def _plan(*, departments=0, speciality=0, groups=0):
    canonical = load_legacy_table_plan()
    counts = {"departments": departments, "speciality": speciality, "groups": groups}
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=sum(counts.values()),
        entries=tuple(replace(canonical.entry_for(table), expected_rows=rows) for table, rows in counts.items()),
    )


def _policy(**overrides):
    values = {
        "phase_keys": ("academic_structure",),
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


def _context(
    *,
    plan,
    factory,
    policy=None,
    run_id=None,
    organization=None,
    actor=None,
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
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=cancellation if cancellation is not None else (lambda: cancelled),
        stdout_note=(notes if notes is not None else []).append,
    )


# ---------------------------------------------------------------------------
# The shared four-table fixture (types 3/4/0/9 plus an orphan parent)
# ---------------------------------------------------------------------------


def _department_rows():
    return [
        _row(DEPARTMENT_STRUCTURE_FIELDS, 1, name="Kollec", department_types_id=0, department_id=0, kollec_or_uni="k"),
        _row(DEPARTMENT_STRUCTURE_FIELDS, 2, name="Kollec", department_types_id=3, department_id=0),
        # The parent carries a HIGHER legacy id: only a topological pass resolves it.
        _row(DEPARTMENT_STRUCTURE_FIELDS, 3, name="Kafedra A", department_types_id=4, department_id=5),
        _row(DEPARTMENT_STRUCTURE_FIELDS, 4, name="Naməlum", department_types_id=9, department_id=0),
        _row(DEPARTMENT_STRUCTURE_FIELDS, 5, name="Fakültə B", department_types_id=3, department_id=0),
        _row(DEPARTMENT_STRUCTURE_FIELDS, 6, name="Orfan", department_types_id=3, department_id=99),
    ]


def _speciality_rows():
    return [
        # The trailing tab is exactly the pollution clean_code has to remove.
        _row(SPECIALITY_STRUCTURE_FIELDS, 10, name="İxtisas A", speciality_code="050620\t", department_id=3),
        _row(SPECIALITY_STRUCTURE_FIELDS, 11, name="", speciality_code="5555", department_id=5),
        _row(SPECIALITY_STRUCTURE_FIELDS, 12, name="İxtisas C", speciality_code="", department_id=99),
    ]


def _group_rows():
    return [
        _row(
            GROUP_STRUCTURE_FIELDS,
            20,
            name="A-19",
            speciality_id=10,
            department_id=3,
            sector="az",
            eyani_qiyabi="Əyani",
            bak_or_mag="bak",
            start_year=2019,
            curricula_id=7,
            kollec_or_uni="uni",
        ),
        _row(
            GROUP_STRUCTURE_FIELDS,
            21,
            name="AM-20",
            speciality_id=10,
            department_id=3,
            sector="EN",
            eyani_qiyabi="Qiyabi",
            bak_or_mag="mag",
            start_year=2020,
            curricula_id=0,
        ),
        _row(
            GROUP_STRUCTURE_FIELDS,
            22,
            name="",
            speciality_id=11,
            department_id=5,
            sector="xx",
            eyani_qiyabi="axşam",
            bak_or_mag="",
            start_year=0,
        ),
        _row(
            GROUP_STRUCTURE_FIELDS,
            23,
            name="C-21",
            speciality_id=12,
            department_id=5,
            sector="ru",
            bak_or_mag="bak",
            start_year=1800,
        ),
        _row(
            GROUP_STRUCTURE_FIELDS,
            24,
            name="Orfan qrup",
            speciality_id=77,
            department_id=5,
            bak_or_mag="bak",
            start_year=2021,
        ),
    ]


def _full_factory():
    return _factory({"departments": _department_rows(), "speciality": _speciality_rows(), "groups": _group_rows()})


def _full_plan():
    return _plan(departments=6, speciality=3, groups=5)


# ---------------------------------------------------------------------------
# Cohort streaming and classification (no database)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("legacy_pk", ["7421", 7421.0, True, None])
def test_cohort_stream_rejects_non_integer_pk(legacy_pk):
    context = _context(
        plan=_plan(departments=1),
        factory=_factory({"departments": [_row(DEPARTMENT_STRUCTURE_FIELDS, legacy_pk)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_type_drift"


@pytest.mark.parametrize("legacy_pk", [0, -1, MAX_LEDGER_PRIMARY_KEY + 1])
def test_cohort_stream_rejects_out_of_range_pk(legacy_pk):
    context = _context(
        plan=_plan(departments=1),
        factory=_factory({"departments": [_row(DEPARTMENT_STRUCTURE_FIELDS, legacy_pk)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_out_of_range"


def test_cohort_stream_rejects_descending_pk():
    context = _context(
        plan=_plan(departments=2),
        factory=_factory({"departments": [_row(DEPARTMENT_STRUCTURE_FIELDS, 7), _row(DEPARTMENT_STRUCTURE_FIELDS, 3)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_order_invalid"


@pytest.mark.parametrize("observed_rows", [1, 3])
def test_cohort_row_count_must_equal_plan_expected_rows(observed_rows):
    context = _context(
        plan=_plan(departments=2),
        factory=_factory(
            {"departments": [_row(DEPARTMENT_STRUCTURE_FIELDS, index) for index in range(1, observed_rows + 1)]}
        ),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_row_count_mismatch"


def test_cohort_refuses_a_table_larger_than_the_bounded_cap():
    context = _context(plan=_plan(groups=source_module.STRUCTURE_COHORT_MAX_ROWS + 1), factory=_factory({}))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_cohort_too_large"


def test_non_integer_start_year_fails_closed():
    context = _context(
        plan=_plan(groups=1),
        factory=_factory({"groups": [_row(GROUP_STRUCTURE_FIELDS, 1, start_year="2019")]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_structure_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_value_type_unsupported"


def test_credential_columns_never_reach_the_cohort():
    factory = _full_factory()

    cohort = build_structure_cohort(_context(plan=_full_plan(), factory=factory))

    assert [department.legacy_pk for department in cohort.departments] == [1, 2, 3, 4, 5, 6]
    assert [speciality.legacy_pk for speciality in cohort.specialities] == [10, 11, 12]
    assert [group.legacy_pk for group in cohort.groups] == [20, 21, 22, 23, 24]
    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 3
    assert all("password" not in statement for statement in statements)
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


def test_department_type_and_name_classification():
    cohort = build_structure_cohort(_context(plan=_full_plan(), factory=_full_factory()))
    by_pk = {department.legacy_pk: department for department in cohort.departments}

    assert by_pk[1].unit_type == OrgUnitType.FACULTY
    assert by_pk[1].rule_codes == ("legacy_structure_department_type_nonstandard",)
    assert by_pk[2].unit_type == OrgUnitType.FACULTY and by_pk[2].rule_codes == ()
    assert by_pk[3].unit_type == OrgUnitType.CHAIR and by_pk[3].parent_legacy_pk == 5
    # An unknown type carries no unit type at all, which is what quarantines it.
    assert by_pk[4].unit_type == "" and by_pk[4].rule_codes == ("legacy_structure_department_type_unknown",)


def test_group_attribute_normalisation():
    cohort = build_structure_cohort(_context(plan=_full_plan(), factory=_full_factory()))
    by_pk = {group.legacy_pk: group for group in cohort.groups}

    assert (by_pk[20].sector, by_pk[20].education_form, by_pk[20].degree_level) == ("az", "full_time", "bachelor")
    assert by_pk[20].admission_year == 2019 and by_pk[20].rule_codes == ()
    assert (by_pk[21].sector, by_pk[21].education_form, by_pk[21].degree_level) == ("en", "part_time", "master")
    assert by_pk[22].sector == "" and by_pk[22].education_form == "" and by_pk[22].admission_year is None
    assert set(by_pk[22].rule_codes) == {
        "legacy_structure_name_blank",
        "legacy_group_sector_unknown",
        "legacy_group_education_form_unknown",
        "legacy_group_degree_level_defaulted",
    }
    assert by_pk[23].admission_year is None
    assert "legacy_group_start_year_invalid" in by_pk[23].rule_codes


def test_program_codes_follow_the_v1_rule():
    """V-1: only ``^\\d{6}$`` is real; "5555" and a blank code fall back to MYEDU."""

    cohort = build_structure_cohort(_context(plan=_full_plan(), factory=_full_factory()))
    by_key = {(plan.speciality_legacy_pk, plan.degree_level): plan for plan in cohort.programs}

    assert sorted(by_key) == [(10, "bachelor"), (10, "master"), (11, "bachelor"), (12, "bachelor")]
    assert by_key[(10, "bachelor")].code == "050620"  # real DIM code, tab stripped
    assert by_key[(10, "master")].code == "050620-M"
    assert by_key[(11, "bachelor")].code == "MYEDU-11"  # the "5555" dummy
    assert by_key[(12, "bachelor")].code == "MYEDU-12"  # blank code
    assert by_key[(10, "bachelor")].ects_total == 240
    assert by_key[(10, "master")].ects_total == 120
    assert by_key[(11, "bachelor")].name == "İxtisas 11"  # blank name fallback


def test_a_speciality_without_groups_defaults_to_bachelor():
    context = _context(
        plan=_plan(speciality=1),
        factory=_factory({"speciality": [_row(SPECIALITY_STRUCTURE_FIELDS, 4, name="Tənha", speciality_code="")]}),
    )

    cohort = build_structure_cohort(context)

    assert [(plan.degree_level, plan.code) for plan in cohort.programs] == [("bachelor", "MYEDU-4")]
    assert cohort.programs[0].rule_codes == ("legacy_speciality_without_groups",)


def test_real_code_collision_is_suffixed_with_the_legacy_id():
    context = _context(
        plan=_plan(speciality=2),
        factory=_factory(
            {
                "speciality": [
                    _row(SPECIALITY_STRUCTURE_FIELDS, 4, name="A", speciality_code="050620"),
                    _row(SPECIALITY_STRUCTURE_FIELDS, 9, name="B", speciality_code=" 050620 "),
                ]
            }
        ),
    )

    cohort = build_structure_cohort(context)

    assert [plan.code for plan in cohort.programs] == ["050620", "050620-9"]
    assert "legacy_program_code_collision" in cohort.programs[1].rule_codes
    assert cohort.programs[0].rule_codes == ("legacy_speciality_without_groups",)


def test_a_second_collision_on_the_same_code_is_unallocatable():
    context = _context(
        plan=_plan(speciality=2),
        factory=_factory(
            {
                "speciality": [
                    _row(SPECIALITY_STRUCTURE_FIELDS, 4, speciality_code="050620"),
                    # Its own suffixed form is already taken by the first row.
                    _row(SPECIALITY_STRUCTURE_FIELDS, 9, speciality_code="050620"),
                ]
            }
        ),
    )
    cohort = build_structure_cohort(context)
    assert [plan.code for plan in cohort.programs] == ["050620", "050620-9"]

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        source_module._allocate_program_code("050620", 9, "bachelor", {"050620", "050620-9"})

    assert exc_info.value.code == "legacy_program_code_unallocatable"


def test_topological_order_places_parents_first_and_isolates_cycles():
    cohort = build_structure_cohort(_context(plan=_full_plan(), factory=_full_factory()))

    ordered, cycled = ordered_departments(cohort.departments)

    assert cycled == ()
    placement = {department.legacy_pk: index for index, department in enumerate(ordered)}
    assert placement[5] < placement[3]  # the higher-id parent is created first


def test_a_parent_cycle_is_detected_without_recursion():
    context = _context(
        plan=_plan(departments=2),
        factory=_factory(
            {
                "departments": [
                    _row(DEPARTMENT_STRUCTURE_FIELDS, 7, name="A", department_types_id=3, department_id=8),
                    _row(DEPARTMENT_STRUCTURE_FIELDS, 8, name="B", department_types_id=3, department_id=7),
                ]
            }
        ),
    )
    cohort = build_structure_cohort(context)

    ordered, cycled = ordered_departments(cohort.departments)

    assert ordered == ()
    assert [department.legacy_pk for department in cycled] == [7, 8]


def test_issue_severity_map_covers_every_structure_rule():
    expected = {
        "legacy_structure_department_type_nonstandard": "warning",
        "legacy_structure_department_type_unknown": "error",
        "legacy_structure_parent_missing": "warning",
        "legacy_structure_parent_cycle": "error",
        "legacy_structure_name_blank": "warning",
        "legacy_structure_name_truncated": "info",
        "legacy_program_code_truncated": "warning",
        "legacy_program_code_collision": "warning",
        "legacy_speciality_without_groups": "info",
        "legacy_group_speciality_missing": "warning",
        "legacy_group_sector_unknown": "info",
        "legacy_group_education_form_unknown": "info",
        "legacy_group_degree_level_defaulted": "info",
        "legacy_group_start_year_invalid": "warning",
    }

    assert dict(ISSUE_SEVERITY) == expected
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


# ---------------------------------------------------------------------------
# Ledger-backed behaviour
# ---------------------------------------------------------------------------


@pytest.fixture()
def structure_environment(db, django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="structure_phase_actor",
        email="structure-phase-actor@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Structure Phase Organization",
        slug="structure-phase-organization",
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


def _full_context(organization, actor, *, policy, plan, factory=None, notes=None, **overrides):
    return _context(
        plan=plan,
        factory=factory if factory is not None else _full_factory(),
        policy=policy,
        organization=organization,
        actor=actor,
        target_validators=build_target_validators(),
        notes=notes,
        **overrides,
    )


@pytest.mark.django_db
def test_phase_run_builds_the_tree_and_seals_its_batches(structure_environment):
    organization, actor = structure_environment
    policy = _policy()
    plan = _full_plan()
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    notes = []
    context = _full_context(organization, actor, policy=policy, plan=plan, notes=notes)
    context = replace(context, run_id=run.pk)

    report = AcademicStructurePhase().run(context)

    assert report.phase_key == "academic_structure"
    assert report.order == 10
    assert report.observed_source_rows == 14 == report.declared_source_rows
    assert dict(report.state_counts) == {"migrated": 13, "skipped": 0, "quarantined": 1}
    assert report.staged_account_count == 13
    assert [(record.source_table, record.sequence) for record in report.batches] == [
        ("departments", 1),
        ("speciality", 1),
        ("groups", 1),
    ]
    assert [(record.first_legacy_pk, record.last_legacy_pk) for record in report.batches] == [
        (1, 6),
        (10, 12),
        (20, 24),
    ]
    assert {batch.source_table: batch.source_row_count for batch in LegacyImportBatch.objects.filter(run=run)} == {
        "departments": 6,
        "speciality": 3,
        "groups": 5,
    }
    assert notes == [
        "academic_structure.departments.batch.1",
        "academic_structure.speciality.batch.1",
        "academic_structure.groups.batch.1",
    ]

    # Two departments literally share the name "Kollec": only a legacy-keyed
    # slug keeps them from colliding on unique_together(organization, slug).
    kollec = OrgUnit.objects.filter(organization=organization, name="Kollec").order_by("slug")
    assert [unit.slug for unit in kollec] == ["myedu-dep-1", "myedu-dep-2"]
    assert OrgUnit.objects.filter(organization=organization).count() == 13
    assert OrgUnit.objects.get(slug="myedu-dep-3").parent.slug == "myedu-dep-5"
    assert OrgUnit.objects.get(slug="myedu-dep-3").unit_type == OrgUnitType.CHAIR
    assert OrgUnit.objects.get(slug="myedu-dep-1").unit_type == OrgUnitType.FACULTY
    assert not OrgUnit.objects.filter(slug="myedu-dep-4").exists()  # type 9 ⇒ quarantined
    assert OrgUnit.objects.get(slug="myedu-dep-6").parent_id is None  # orphan parent
    assert OrgUnit.objects.get(slug="myedu-spec-10").parent.slug == "myedu-dep-3"
    assert OrgUnit.objects.get(slug="myedu-grp-20").parent.slug == "myedu-spec-10"
    assert OrgUnit.objects.get(slug="myedu-grp-24").parent.slug == "myedu-dep-5"  # speciality fallback


@pytest.mark.django_db
def test_phase_run_writes_settings_programs_and_issues(structure_environment):
    organization, actor = structure_environment
    policy = _policy()
    plan = _full_plan()
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    context = replace(_full_context(organization, actor, policy=policy, plan=plan), run_id=run.pk)

    AcademicStructurePhase().run(context)

    assert OrgUnit.objects.get(slug="myedu-grp-20").settings == {
        "education_form": "full_time",
        "admission_year": 2019,
        "sector": "az",
        "degree_level": "bachelor",
        "legacy": {
            "source_system": SOURCE_SYSTEM,
            "table": "groups",
            "id": 20,
            "speciality_id": 10,
            "department_id": 3,
            "curricula_id": 7,
            "kollec_or_uni": "uni",
        },
    }
    assert OrgUnit.objects.get(slug="myedu-dep-1").settings == {
        "legacy": {
            "source_system": SOURCE_SYSTEM,
            "table": "departments",
            "id": 1,
            "parent_id": 0,
            "type_id": 0,
            "kollec_or_uni": "k",
        }
    }
    assert OrgUnit.objects.get(slug="myedu-spec-10").code == "050620"

    programs = Program.objects.filter(organization=organization).order_by("code")
    assert [(program.code, program.degree_level, program.ects_total) for program in programs] == [
        ("050620", "bachelor", 240),
        ("050620-M", "master", 120),
        ("MYEDU-11", "bachelor", 240),
        ("MYEDU-12", "bachelor", 240),
    ]
    assert {program.specialty_unit.slug for program in programs} == {
        "myedu-spec-10",
        "myedu-spec-11",
        "myedu-spec-12",
    }

    # One batch-accounted map per source row, plus the four derived programs.
    assert LegacyEntityMap.objects.filter(entity_type="speciality_program").count() == 4
    assert LegacyEntityMap.objects.filter(entity_type="speciality_program", legacy_pk="10:master").get().state == (
        LegacyEntityMap.State.MIGRATED
    )
    assert LegacyEntityObservation.objects.filter(run=run).count() == 18
    assert (
        LegacyEntityObservation.objects.get(
            run=run, entity_map__entity_type="department_unit", entity_map__legacy_pk="4"
        ).state
        == LegacyEntityMap.State.QUARANTINED
    )

    issues = {(issue.legacy_pk, issue.rule_code): issue.severity for issue in LegacyMigrationIssue.objects.all()}
    assert issues[("4", "legacy_structure_department_type_unknown")] == "error"
    assert issues[("1", "legacy_structure_department_type_nonstandard")] == "warning"
    assert issues[("6", "legacy_structure_parent_missing")] == "warning"
    assert issues[("12", "legacy_structure_parent_missing")] == "warning"
    assert issues[("24", "legacy_group_speciality_missing")] == "warning"
    assert issues[("23", "legacy_group_start_year_invalid")] == "warning"
    assert issues[("22", "legacy_group_sector_unknown")] == "info"
    assert issues[("11", "legacy_structure_name_blank")] == "warning"
    assert ("4", "legacy_structure_department_type_unknown") in issues
    assert all(
        target_label in ("", ORG_UNIT_MODEL_LABEL, PROGRAM_MODEL_LABEL)
        for target_label in LegacyEntityMap.objects.values_list("target_model_label", flat=True)
    )


@pytest.mark.django_db
def test_phase_run_replays_identically_and_detects_drift(structure_environment):
    organization, actor = structure_environment
    policy = _policy(batch_rows=2)
    plan = _full_plan()
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    context = replace(_full_context(organization, actor, policy=policy, plan=plan), run_id=run.pk)

    report = AcademicStructurePhase().run(context)

    assert [(record.source_table, record.sequence) for record in report.batches] == [
        ("departments", 1),
        ("departments", 2),
        ("departments", 3),
        ("speciality", 1),
        ("speciality", 2),
        ("groups", 1),
        ("groups", 2),
        ("groups", 3),
    ]

    replay = AcademicStructurePhase().run(context)

    assert replay == report
    assert LegacyImportBatch.objects.filter(run=run).count() == 8
    assert LegacyEntityObservation.objects.filter(run=run).count() == 18
    assert OrgUnit.objects.filter(organization=organization).count() == 13

    # Department 2 carries no issue of its own, so the drift reaches the batch
    # replay check instead of tripping the ledger's issue-identity guard first.
    mutated = _department_rows()
    mutated[1]["name"] = "Kollec (yenilənmiş)"
    drifted = replace(
        context,
        source_connection_factory=_factory(
            {"departments": mutated, "speciality": _speciality_rows(), "groups": _group_rows()}
        ),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        AcademicStructurePhase().run(drifted)

    assert exc_info.value.code == "legacy_rehearsal_batch_replay_mismatch"


@pytest.mark.django_db
def test_phase_run_quarantines_a_parent_cycle(structure_environment):
    organization, actor = structure_environment
    policy = _policy()
    plan = _plan(departments=2)
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=2)
    factory = _factory(
        {
            "departments": [
                _row(DEPARTMENT_STRUCTURE_FIELDS, 7, name="A", department_types_id=3, department_id=8),
                _row(DEPARTMENT_STRUCTURE_FIELDS, 8, name="B", department_types_id=3, department_id=7),
            ]
        }
    )
    context = replace(_full_context(organization, actor, policy=policy, plan=plan, factory=factory), run_id=run.pk)

    report = AcademicStructurePhase().run(context)

    assert dict(report.state_counts) == {"migrated": 0, "skipped": 0, "quarantined": 2}
    assert OrgUnit.objects.filter(organization=organization).count() == 0
    assert set(LegacyMigrationIssue.objects.values_list("rule_code", "severity")) == {
        ("legacy_structure_parent_cycle", "error")
    }


@pytest.mark.django_db
def test_phase_run_stops_on_a_cancellation_request(structure_environment):
    organization, actor = structure_environment
    policy = _policy()
    plan = _full_plan()
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    requested = {"cancelled": False}
    closed = {"streams": 0}

    def arming_factory():
        """Arm the phase-level interlock only once every source stream is closed."""

        inner = _full_factory()

        def build():
            connection = inner()
            original_close = connection.close

            def close():
                original_close()
                closed["streams"] += 1
                if closed["streams"] == len(_CONTRACTS):
                    requested["cancelled"] = True

            connection.close = close
            return connection

        return build

    context = replace(
        _full_context(
            organization,
            actor,
            policy=policy,
            plan=plan,
            factory=arming_factory(),
            cancellation=lambda: requested["cancelled"],
        ),
        run_id=run.pk,
    )

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        AcademicStructurePhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    assert LegacyEntityObservation.objects.filter(run=run).count() == 0
    assert OrgUnit.objects.filter(organization=organization).count() == 0

    # A cancellation raised before the first row closes the source transport
    # instead, which is the extractor's own contract.
    with pytest.raises(LegacySourceExtractionCancelled):
        AcademicStructurePhase().run(
            replace(_full_context(organization, actor, policy=policy, plan=plan, cancelled=True), run_id=run.pk)
        )

    assert LegacyImportBatch.objects.filter(run=run).count() == 0


@pytest.mark.django_db
def test_phase_refuses_a_non_university_organization(structure_environment):
    _organization, actor = structure_environment
    school = Organization.objects.create(
        name="Structure Phase School",
        slug="structure-phase-school",
        org_type=OrganizationType.SCHOOL,
        owner=actor,
        status="active",
        is_active=True,
    )
    context = _full_context(school, actor, policy=_policy(), plan=_full_plan())

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        AcademicStructurePhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_organization_type_unsupported"


def test_phase_refuses_a_foreign_context_object():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        AcademicStructurePhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


# ---------------------------------------------------------------------------
# Refactor pin: §3.5 extracted ``group_admission_year`` out of ``_group``
# ---------------------------------------------------------------------------

# Captured from the shipped fixture BEFORE the extraction.  ``group_admission_year``
# is behaviour-preserving by contract, and the classification chain is exactly
# ``(legacy_pk, state, decision_token)`` — the group token carries the derived
# admission year — so these bytes must survive the refactor unchanged.
_PINNED_CLASSIFICATION_DIGESTS = {
    "departments": "4b4a20a999973d5d97eedd44dbbf868437e0ffbf894fa3c546a46d2f24e08d39",
    "speciality": "002c415228e1701390b9c50a2040c1b49659f87f348f4dd205f887cdd8b22733",
    "groups": "94278e4a58715159076e35474916a395113c00fc6a301afd4065bb8adb324c46",
}


@pytest.mark.django_db
def test_classification_digests_are_pinned_across_the_group_year_refactor(structure_environment):
    organization, actor = structure_environment
    policy = _policy()
    plan = _full_plan()
    run = _running_run(organization, actor, policy=policy, plan=plan, source_row_count=14)
    context = replace(_full_context(organization, actor, policy=policy, plan=plan), run_id=run.pk)

    report = AcademicStructurePhase().run(context)

    assert {
        record.source_table: record.classification_digest for record in report.batches
    } == _PINNED_CLASSIFICATION_DIGESTS


def test_group_admission_year_classifies_the_year_sentinel_and_range():
    assert source_module.group_admission_year(2019) == (2019, ())
    assert source_module.group_admission_year(0) == (None, ())
    assert source_module.group_admission_year(None) == (None, ())
    assert source_module.group_admission_year(1800) == (None, ("legacy_group_start_year_invalid",))
    assert source_module.group_admission_year(source_module.MIN_ADMISSION_YEAR) == (
        source_module.MIN_ADMISSION_YEAR,
        (),
    )
    assert source_module.group_admission_year(source_module.MAX_ADMISSION_YEAR + 1) == (
        None,
        ("legacy_group_start_year_invalid",),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        source_module.group_admission_year("2019")

    assert exc_info.value.code == "legacy_rehearsal_source_value_type_unsupported"
