"""Phase ``academic_catalog`` tests: targets, ledger rows, batches and replay.

The fixture runs the SHIPPED ``academic_structure`` phase first, in the same run,
because that is the only supported way for the catalogue to see a ``Program``:
the resolution index is built from THIS run's ``speciality_program`` maps.
"""

from dataclasses import replace

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyImportBatch,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.field_contracts import (
    CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS,
    DEPARTMENT_STRUCTURE_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    LESSON_CATALOG_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
)
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.rehearsal_authorizer import (
    CURRICULUM_MODEL_LABEL,
    CURRICULUM_SUBJECT_MODEL_LABEL,
    SUBJECT_MODEL_LABEL,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_catalog_phase import ISSUE_SEVERITY, AcademicCatalogPhase
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
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from apps.legacy_import.services.rehearsal_structure_phase import AcademicStructurePhase
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import Organization
from apps.registrar.models import Curriculum, CurriculumSubject, Program, Subject
from core.constants import OrganizationType

_SNAPSHOT_SHA256 = load_legacy_table_plan().source_snapshot_sha256
_CONTRACTS = {
    "departments": DEPARTMENT_STRUCTURE_FIELDS,
    "speciality": SPECIALITY_STRUCTURE_FIELDS,
    "groups": GROUP_STRUCTURE_FIELDS,
    "lessons": LESSON_CATALOG_FIELDS,
    "curricula": CURRICULUM_CATALOG_FIELDS,
    "curricula_plan": CURRICULUM_PLAN_FIELDS,
}
# Decoy authentication columns that must never leave the source.
_CREDENTIAL_COLUMNS = ("password", "show_password", "pin_for_lock")
_TABLE_COUNTS = {
    "departments": 1,
    "speciality": 2,
    "groups": 4,
    "lessons": 5,
    "curricula": 4,
    "curricula_plan": 8,
}


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


def _plan(**overrides):
    canonical = load_legacy_table_plan()
    counts = {**_TABLE_COUNTS, **overrides}
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=sum(counts.values()),
        entries=tuple(replace(canonical.entry_for(table), expected_rows=rows) for table, rows in counts.items()),
    )


def _policy(**overrides):
    values = {
        "phase_keys": ("academic_structure", "academic_catalog"),
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


def _context(*, plan, factory, policy, organization=None, actor=None, run_id=None, cancellation=None, notes=None):
    return RehearsalContext(
        run_id=run_id,
        organization=organization,
        actor=actor,
        authorize=_allow,
        target_validators=build_target_validators(),
        policy=policy,
        plan=plan,
        source_connection_factory=factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=cancellation if cancellation is not None else (lambda: False),
        stdout_note=(notes if notes is not None else []).append,
    )


# ---------------------------------------------------------------------------
# The shared fixture: 1 department · 2 specialities · 4 groups
#                     5 lessons · 4 curricula · 8 plan rows
# ---------------------------------------------------------------------------


def _lesson(legacy_pk, **overrides):
    values = {"name": f"Fənn {legacy_pk}", "lesson_code": "37", "type": "1", "department_id": 3, "only_az": 0}
    values.update(overrides)
    return _row(LESSON_CATALOG_FIELDS, legacy_pk, **values)


def _curriculum(legacy_pk, **overrides):
    values = {"speciality_id": 10, "from_date": "", "to_date": "2023", "eyani_qiyabi": "", "bak_or_mag": "bak"}
    values.update(overrides)
    return _row(CURRICULUM_CATALOG_FIELDS, legacy_pk, **values)


def _plan_row(legacy_pk, **overrides):
    values = {
        "curricula_id": 100,
        "lesson_id": '["1"]',
        "lesson_code": "37",
        "type": "3",
        "semestr": "payiz_1",
        "kredit": 6.0,
        "lesson_before_id": 0,
        "saat_aks": 0.0,
        "saat_as": 0.0,
        "saat_muh": 0.0,
        "saat_sem": 0.0,
        "saat_lab": 0.0,
        "saat_prak": 0.0,
    }
    values.update(overrides)
    return _row(CURRICULUM_PLAN_FIELDS, legacy_pk, **values)


def _group(legacy_pk, **overrides):
    values = {
        "speciality_id": 10,
        "department_id": 1,
        "name": f"A-{legacy_pk}",
        "sector": "az",
        "eyani_qiyabi": "Əyani",
        "bak_or_mag": "bak",
        "start_year": 2019,
        "curricula_id": 100,
        "kollec_or_uni": "uni",
    }
    values.update(overrides)
    return _row(GROUP_STRUCTURE_FIELDS, legacy_pk, **values)


def _lesson_rows():
    return [
        _lesson(1, name="Riyaziyyat"),
        # Same name in the same department ⇒ deduplicated onto lesson 1 (E-4).
        _lesson(2, name="  RIYAZIYYAT  "),
        _lesson(3, name="Fizika"),
        _lesson(4, name=""),
        # Same name, DIFFERENT department ⇒ its own subject.
        _lesson(5, name="Fizika", department_id=4),
    ]


def _source_rows():
    return {
        "departments": [_row(DEPARTMENT_STRUCTURE_FIELDS, 1, name="Fakültə", department_types_id=3, department_id=0)],
        "speciality": [
            _row(SPECIALITY_STRUCTURE_FIELDS, 10, name="İxtisas A", speciality_code="050620", department_id=1),
            _row(SPECIALITY_STRUCTURE_FIELDS, 11, name="İxtisas B", speciality_code="", department_id=1),
        ],
        "groups": [
            _group(20, start_year=2021, curricula_id=100),
            _group(21, start_year=2019, curricula_id=100),
            _group(22, speciality_id=11, start_year=2020, curricula_id=0),
            _group(23, start_year=2019, curricula_id=102),
        ],
        "lessons": _lesson_rows(),
        "curricula": [
            _curriculum(100, eyani_qiyabi="Əyani"),
            # V-20 T3: no group points at it and ``from_date`` is empty, so the
            # year is INFERRED from ``to_date`` (2023 − 4) instead of quarantined.
            _curriculum(101),
            # Same (program, 2019) as 100 ⇒ merges onto the very same row.
            _curriculum(102),
            # speciality 11 has only BACHELOR groups, so "11:master" resolves to
            # no Program and this phase refuses to mint one (SA-1).
            _curriculum(103, speciality_id=11, bak_or_mag="mag", from_date="2020"),
        ],
        "curricula_plan": [
            _plan_row(1, lesson_id='["1"]', kredit=6.0, semestr="payiz_1", saat_muh=30.0),
            _plan_row(2, lesson_id='["3"]', kredit=4.0, semestr="yaz_2", type="1", lesson_before_id=1),
            # Lesson 2 dedups onto subject 1 ⇒ the plan row is a duplicate.
            _plan_row(3, lesson_id='["2"]', kredit=6.0, semestr="payiz_1"),
            # V-14: two elements ⇒ two CurriculumSubject rows from ONE source row.
            _plan_row(4, lesson_id='["1","3"]', kredit=0.0, semestr="payiz_3", type=""),
            # V-14: one element resolves, one does not ⇒ partial, still migrated.
            # V-21: ``4.01`` is an elective block, and rows 5 and 7 land in the
            # SAME (curriculum, semester, block) triple — one block, two choices.
            _plan_row(5, lesson_id='["4","9999"]', kredit=3.0, semestr="yaz_2", type="4.01"),
            # V-21: a token in neither family is the only ``type_unmapped`` case
            # left; the live dump is not expected to carry one at all.
            _plan_row(6, lesson_id='["9999"]', kredit=3.0, semestr="payiz_1", type="2.1.3"),
            # V-13: ``payiz`` with an EVEN ordinal contradicts the scheme.
            _plan_row(7, lesson_id='["5"]', kredit=2.5, semestr="payiz_2", type="4.01"),
            # Curriculum 103 is quarantined, so this row has no plan to hang on.
            _plan_row(8, curricula_id=103, lesson_id='["3"]', kredit=5.0, semestr="yaz_2", type="2.1"),
        ],
    }


@pytest.fixture()
def catalog_environment(db, django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="catalog_phase_actor",
        email="catalog-phase-actor@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Catalog Phase Organization",
        slug="catalog-phase-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    return organization, actor


def _running_run(organization, actor, *, policy, plan):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=_SNAPSHOT_SHA256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=plan.expected_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{plan.fingerprint[:12]}",
        transform_version=policy.transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _structured_context(organization, actor, *, policy=None, rows=None, notes=None, **overrides):
    """Run the structure phase first; return the context the catalogue inherits."""

    policy = policy or _policy()
    plan = _plan()
    run = _running_run(organization, actor, policy=policy, plan=plan)
    context = _context(
        plan=plan,
        factory=_factory(rows if rows is not None else _source_rows()),
        policy=policy,
        organization=organization,
        actor=actor,
        run_id=run.pk,
        notes=notes,
        **overrides,
    )
    AcademicStructurePhase().run(context)
    return context, run


def _catalog_issues():
    return {
        (issue.source_table, issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(source_table__in=("lessons", "curricula", "curricula_plan"))
    }


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def test_phase_refuses_a_foreign_context_object():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        AcademicCatalogPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_phase_refuses_a_run_without_the_structure_phase():
    context = _context(
        plan=_plan(),
        factory=_factory(_source_rows()),
        policy=_policy(phase_keys=("academic_catalog",)),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        AcademicCatalogPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_phase_declares_the_three_catalogue_tables():
    phase = AcademicCatalogPhase()

    assert (phase.phase_key, phase.order) == ("academic_catalog", 12)
    assert phase.source_tables == ("lessons", "curricula", "curricula_plan")
    assert phase.entity_types == ("lesson_subject", "curriculum_plan", "curriculum_plan_row")
    assert phase.declared_source_rows(load_legacy_table_plan()) == 2521 + 126 + 3424


def test_issue_severity_map_covers_every_catalogue_rule():
    expected = {
        "legacy_subject_name_blank": "warning",
        "legacy_subject_name_truncated": "info",
        "legacy_subject_deduplicated": "info",
        "legacy_subject_ects_unavailable": "info",
        "legacy_subject_ects_ambiguous": "warning",
        "legacy_curriculum_program_unresolved": "warning",
        "legacy_curriculum_degree_defaulted": "info",
        # V-20: the two derived tiers of the admission-year ladder.
        "legacy_curriculum_admission_year_inferred": "warning",
        "legacy_curriculum_admission_year_neighbor": "warning",
        "legacy_curriculum_admission_year_unresolved": "warning",
        "legacy_curriculum_merged_into_existing": "warning",
        "legacy_curriculum_education_form_not_modelled": "info",
        "legacy_plan_curriculum_unresolved": "warning",
        "legacy_plan_lesson_reference_invalid": "warning",
        "legacy_plan_lesson_reference_expanded": "info",
        "legacy_plan_lesson_reference_partial": "warning",
        "legacy_plan_lesson_unresolved": "warning",
        "legacy_plan_semester_invalid": "warning",
        "legacy_plan_semester_out_of_range": "warning",
        "legacy_plan_semester_scheme_conflict": "warning",
        # V-21: the elective block the university confirmed, and the token that
        # matched neither family.
        "legacy_plan_elective_block": "info",
        "legacy_plan_type_unmapped": "info",
        "legacy_plan_credit_unsupported": "info",
        "legacy_plan_hours_not_modelled": "info",
        "legacy_plan_prerequisite_not_modelled": "info",
        "legacy_plan_row_duplicate": "warning",
    }

    assert dict(ISSUE_SEVERITY) == expected
    # E-13: the first catalogue rehearsal must be able to reach SUCCEEDED.
    assert set(ISSUE_SEVERITY.values()) == {"info", "warning"}


# ---------------------------------------------------------------------------
# The full run
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_phase_run_builds_the_catalogue_and_seals_its_batches(catalog_environment):
    organization, actor = catalog_environment
    notes = []
    context, run = _structured_context(organization, actor, notes=notes)

    report = AcademicCatalogPhase().run(context)

    assert (report.phase_key, report.order) == ("academic_catalog", 12)
    assert report.observed_source_rows == 17 == report.declared_source_rows
    # V-20 moved curriculum 101 out of quarantine, which also rescued nothing
    # else: the two remaining quarantines are a real lesson and a real program miss.
    assert dict(report.state_counts) == {"migrated": 14, "skipped": 0, "quarantined": 3}
    assert report.staged_account_count == 14
    assert [(record.source_table, record.sequence) for record in report.batches] == [
        ("lessons", 1),
        ("curricula", 1),
        ("curricula_plan", 1),
    ]
    assert [(record.first_legacy_pk, record.last_legacy_pk) for record in report.batches] == [
        (1, 5),
        (100, 103),
        (1, 8),
    ]
    assert {
        batch.source_table: batch.source_row_count
        for batch in LegacyImportBatch.objects.filter(run=run, source_table__in=_CONTRACTS)
        if batch.source_table in ("lessons", "curricula", "curricula_plan")
    } == {"lessons": 5, "curricula": 4, "curricula_plan": 8}
    assert notes[-3:] == [
        "academic_catalog.lessons.batch.1",
        "academic_catalog.curricula.batch.1",
        "academic_catalog.curricula_plan.batch.1",
    ]


@pytest.mark.django_db
def test_phase_run_deduplicates_subjects_and_derives_ects(catalog_environment):
    organization, actor = catalog_environment
    context, run = _structured_context(organization, actor)

    AcademicCatalogPhase().run(context)

    subjects = Subject.objects.filter(organization=organization).order_by("code")
    assert [(subject.code, subject.name, subject.ects) for subject in subjects] == [
        ("MYEDU-L1", "Riyaziyyat", 6),  # one accepted kredit ⇒ used verbatim
        ("MYEDU-L3", "Fizika", 5),  # 4.0 and 5.0 ⇒ ambiguous ⇒ the model default
        ("MYEDU-L4", "Fənn 4", 3),  # blank name ⇒ a legacy-keyed fallback
        ("MYEDU-L5", "Fizika", 5),  # only a 2.5 ⇒ never rounded ⇒ unavailable
    ]
    assert all(subject.description == "" and subject.is_active for subject in subjects)
    # Five source rows, five maps, but only four subjects: the non-winner points
    # at the winner's row so batch accounting stays 1:1 with ``lessons``.
    maps = LegacyEntityMap.objects.filter(entity_type="lesson_subject").order_by("legacy_pk")
    assert [item.legacy_pk for item in maps] == ["1", "2", "3", "4", "5"]
    assert {item.target_model_label for item in maps} == {SUBJECT_MODEL_LABEL}
    by_code = {subject.code: str(subject.pk) for subject in subjects}
    assert maps.get(legacy_pk="2").target_pk == by_code["MYEDU-L1"]

    issues = _catalog_issues()
    assert issues[("lessons", "2", "legacy_subject_deduplicated")] == "info"
    assert issues[("lessons", "4", "legacy_subject_name_blank")] == "warning"
    assert issues[("lessons", "3", "legacy_subject_ects_ambiguous")] == "warning"
    assert issues[("lessons", "5", "legacy_subject_ects_unavailable")] == "info"
    assert ("lessons", "1", "legacy_subject_ects_unavailable") not in issues
    assert LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type="lesson_subject").count() == 5


@pytest.mark.django_db
def test_phase_run_resolves_programs_merges_and_quarantines_curricula(catalog_environment):
    organization, actor = catalog_environment
    context, _run = _structured_context(organization, actor)

    AcademicCatalogPhase().run(context)

    curricula = Curriculum.objects.filter(organization=organization)
    assert curricula.count() == 1
    curriculum = curricula.get()
    assert (curriculum.program.code, curriculum.admission_year, curriculum.name) == ("050620", 2019, "")
    assert curriculum.program == Program.objects.get(organization=organization, code="050620")

    states = dict(LegacyEntityMap.objects.filter(entity_type="curriculum_plan").values_list("legacy_pk", "state"))
    assert states == {
        "100": LegacyEntityMap.State.MIGRATED,
        # V-20: 101's year is inferred from ``to_date``, so it migrates and then
        # merges instead of dragging its plan rows into quarantine with it.
        "101": LegacyEntityMap.State.MIGRATED,
        "102": LegacyEntityMap.State.MIGRATED,
        "103": LegacyEntityMap.State.QUARANTINED,
    }
    # 100, 101 and 102 are three legacy rows on ONE target row (uniq_curriculum_program_year).
    targets = dict(
        LegacyEntityMap.objects.filter(entity_type="curriculum_plan", state=LegacyEntityMap.State.MIGRATED).values_list(
            "legacy_pk", "target_pk"
        )
    )
    assert targets["100"] == targets["101"] == targets["102"] == str(curriculum.pk)
    assert set(
        LegacyEntityMap.objects.filter(entity_type="curriculum_plan").values_list("target_model_label", flat=True)
    ) == {"", CURRICULUM_MODEL_LABEL}

    issues = _catalog_issues()
    assert issues[("curricula", "100", "legacy_curriculum_education_form_not_modelled")] == "info"
    assert issues[("curricula", "101", "legacy_curriculum_admission_year_inferred")] == "warning"
    assert issues[("curricula", "101", "legacy_curriculum_merged_into_existing")] == "warning"
    assert issues[("curricula", "102", "legacy_curriculum_merged_into_existing")] == "warning"
    assert issues[("curricula", "103", "legacy_curriculum_program_unresolved")] == "warning"
    assert ("curricula", "100", "legacy_curriculum_merged_into_existing") not in issues
    # V-20's target is ZERO year-quarantines, and the fixture reaches it.
    assert not LegacyMigrationIssue.objects.filter(rule_code="legacy_curriculum_admission_year_unresolved").exists()


@pytest.mark.django_db
def test_phase_run_expands_plan_rows_and_ranks_them(catalog_environment):
    organization, actor = catalog_environment
    context, _run = _structured_context(organization, actor)

    AcademicCatalogPhase().run(context)

    rows = CurriculumSubject.objects.filter(organization=organization).order_by(
        "semester_number", "order", "subject__code"
    )
    assert [(row.subject.code, row.semester_number, row.order) for row in rows] == [
        ("MYEDU-L1", 1, 0),
        ("MYEDU-L3", 2, 0),
        ("MYEDU-L4", 2, 1),
        ("MYEDU-L5", 2, 2),  # V-13: payiz_2 is semester 2 under ORDINAL
        ("MYEDU-L1", 3, 0),  # V-14: both halves of '["1","3"]'
        ("MYEDU-L3", 3, 0),
    ]
    # V-21: the elective shape is READ from ``type``, never invented — rows 5 and
    # 7 form one block of two alternatives, everything else stays mandatory.
    assert {(row.subject.code, row.is_elective, row.elective_group, row.required_choices) for row in rows} == {
        ("MYEDU-L1", False, "", 1),
        ("MYEDU-L3", False, "", 1),
        ("MYEDU-L4", True, "4.01", 1),
        ("MYEDU-L5", True, "4.01", 1),
    }

    states = dict(LegacyEntityMap.objects.filter(entity_type="curriculum_plan_row").values_list("legacy_pk", "state"))
    assert states == {
        "1": LegacyEntityMap.State.MIGRATED,
        "2": LegacyEntityMap.State.MIGRATED,
        "3": LegacyEntityMap.State.MIGRATED,
        "4": LegacyEntityMap.State.MIGRATED,
        "5": LegacyEntityMap.State.MIGRATED,
        "6": LegacyEntityMap.State.QUARANTINED,
        "7": LegacyEntityMap.State.MIGRATED,
        "8": LegacyEntityMap.State.QUARANTINED,
    }
    # The map of an expanded row points at the FIRST of its target rows (V-14).
    expanded = LegacyEntityMap.objects.get(entity_type="curriculum_plan_row", legacy_pk="4")
    assert expanded.target_model_label == CURRICULUM_SUBJECT_MODEL_LABEL
    assert expanded.target_pk == str(CurriculumSubject.objects.get(subject__code="MYEDU-L1", semester_number=3).pk)

    issues = _catalog_issues()
    assert issues[("curricula_plan", "4", "legacy_plan_lesson_reference_expanded")] == "info"
    assert issues[("curricula_plan", "5", "legacy_plan_lesson_reference_expanded")] == "info"
    assert issues[("curricula_plan", "5", "legacy_plan_lesson_reference_partial")] == "warning"
    assert issues[("curricula_plan", "6", "legacy_plan_lesson_unresolved")] == "warning"
    assert issues[("curricula_plan", "3", "legacy_plan_row_duplicate")] == "warning"
    assert issues[("curricula_plan", "7", "legacy_plan_semester_scheme_conflict")] == "warning"
    assert issues[("curricula_plan", "7", "legacy_plan_credit_unsupported")] == "info"
    assert issues[("curricula_plan", "8", "legacy_plan_curriculum_unresolved")] == "warning"
    assert issues[("curricula_plan", "1", "legacy_plan_hours_not_modelled")] == "info"
    assert issues[("curricula_plan", "2", "legacy_plan_prerequisite_not_modelled")] == "info"
    assert ("curricula_plan", "4", "legacy_plan_credit_unsupported") not in issues  # V-16
    # V-21: the integer tokens 1/3 and the blank are MAPPED (mandatory), so the
    # unmapped code is left with the one token that matches neither family.
    unmapped = [key for key in issues if key[2] == "legacy_plan_type_unmapped"]
    assert sorted(key[1] for key in unmapped) == ["6"]
    elective = [key for key in issues if key[2] == "legacy_plan_elective_block"]
    assert sorted(key[1] for key in elective) == ["5", "7", "8"]
    assert issues[("curricula_plan", "5", "legacy_plan_elective_block")] == "info"


@pytest.mark.django_db
def test_an_undated_curriculum_adopts_a_dated_neighbour(catalog_environment):
    """V-20 T4: the last resort still produces a real, mergeable ``Curriculum``."""

    organization, actor = catalog_environment
    rows = _source_rows()
    # No ``from_date``, no group and no ``to_date`` ⇒ T1..T3 all decline, so the
    # nearest dated neighbour below (curriculum 100, 2019) answers instead.
    rows["curricula"][1] = _curriculum(101, to_date="")
    context, _run = _structured_context(organization, actor, rows=rows)

    AcademicCatalogPhase().run(context)

    curriculum = Curriculum.objects.get(organization=organization)
    assert curriculum.admission_year == 2019
    states = dict(LegacyEntityMap.objects.filter(entity_type="curriculum_plan").values_list("legacy_pk", "state"))
    assert states["101"] == LegacyEntityMap.State.MIGRATED
    issues = _catalog_issues()
    assert issues[("curricula", "101", "legacy_curriculum_admission_year_neighbor")] == "warning"
    assert ("curricula", "101", "legacy_curriculum_admission_year_inferred") not in issues
    assert ("curricula", "101", "legacy_curriculum_admission_year_unresolved") not in issues


@pytest.mark.django_db
def test_elective_rows_form_one_block_per_curriculum_and_semester(catalog_environment):
    """V-21: ``(curriculum, semester, elective_group)`` is the block identity."""

    organization, actor = catalog_environment
    context, _run = _structured_context(organization, actor)

    AcademicCatalogPhase().run(context)

    block = CurriculumSubject.objects.filter(organization=organization, is_elective=True).order_by("subject__code")
    assert [(row.subject.code, row.semester_number, row.elective_group) for row in block] == [
        ("MYEDU-L4", 2, "4.01"),
        ("MYEDU-L5", 2, "4.01"),
    ]
    # One block, so the two alternatives share a curriculum and a semester …
    assert len({(row.curriculum_id, row.semester_number, row.elective_group) for row in block}) == 1
    # … and each of them is a single choice out of it.
    assert {row.required_choices for row in block} == {1}
    mandatory = CurriculumSubject.objects.filter(organization=organization, is_elective=False)
    assert mandatory.count() == 4
    assert set(mandatory.values_list("elective_group", flat=True)) == {""}


@pytest.mark.django_db
def test_the_elective_shape_is_sealed_into_the_target_digest(catalog_environment):
    """V-21 replaced the plan digest's reserved ``"0"`` — every digest changed."""

    organization, actor = catalog_environment
    baseline = AcademicCatalogPhase().run(_structured_context(organization, actor)[0])

    second_tenant = Organization.objects.create(
        name="Catalog Phase Organization II",
        slug="catalog-phase-organization-ii",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    mutated = _source_rows()
    mutated["curricula_plan"][6]["type"] = "3"  # row 7: an elective becomes mandatory
    other = AcademicCatalogPhase().run(_structured_context(second_tenant, actor, rows=mutated)[0])

    by_table = {record.source_table: record for record in baseline.batches}
    other_by_table = {record.source_table: record for record in other.batches}
    # No target UUID reaches a digest, so two tenants over the same source agree
    # everywhere the source agrees …
    assert by_table["lessons"].target_digest == other_by_table["lessons"].target_digest
    assert by_table["curricula"].target_digest == other_by_table["curricula"].target_digest
    # … and the ONLY thing that differs about row 7 inside the semantic digest is
    # its elective encoding, so the target digest has to move with it.
    assert by_table["curricula_plan"].target_digest != other_by_table["curricula_plan"].target_digest
    assert by_table["curricula_plan"].classification_digest != other_by_table["curricula_plan"].classification_digest


@pytest.mark.django_db
def test_term_pair_scheme_moves_every_plan_row(catalog_environment):
    organization, actor = catalog_environment
    context, _run = _structured_context(
        organization, actor, policy=_policy(plan_semester_scheme=PlanSemesterScheme.TERM_PAIR)
    )

    AcademicCatalogPhase().run(context)

    rows = CurriculumSubject.objects.filter(organization=organization)
    assert sorted({row.semester_number for row in rows}) == [1, 3, 4, 5]
    # Under TERM_PAIR the parity check is vacuous by construction.
    assert not LegacyMigrationIssue.objects.filter(rule_code="legacy_plan_semester_scheme_conflict").exists()


@pytest.mark.django_db
def test_phase_run_replays_identically_and_detects_drift(catalog_environment):
    organization, actor = catalog_environment
    context, run = _structured_context(organization, actor, policy=_policy(batch_rows=3))

    report = AcademicCatalogPhase().run(context)

    assert [(record.source_table, record.sequence) for record in report.batches] == [
        ("lessons", 1),
        ("lessons", 2),
        ("curricula", 1),
        ("curricula", 2),
        ("curricula_plan", 1),
        ("curricula_plan", 2),
        ("curricula_plan", 3),
    ]

    replay = AcademicCatalogPhase().run(context)

    assert replay == report
    assert Subject.objects.filter(organization=organization).count() == 4
    assert Curriculum.objects.filter(organization=organization).count() == 1
    assert CurriculumSubject.objects.filter(organization=organization).count() == 6
    assert LegacyEntityObservation.objects.filter(run=run, entity_map__entity_type="lesson_subject").count() == 5

    # ``only_az`` is decision-token evidence and carries no issue of its own, so
    # the drift reaches the batch replay check instead of the ledger's guards.
    mutated = _source_rows()
    mutated["lessons"][0]["only_az"] = 1
    drifted = replace(context, source_connection_factory=_factory(mutated))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        AcademicCatalogPhase().run(drifted)

    assert exc_info.value.code == "legacy_rehearsal_batch_replay_mismatch"


@pytest.mark.django_db
def test_phase_run_stops_on_a_cancellation_request(catalog_environment):
    organization, actor = catalog_environment
    requested = {"cancelled": False}
    context, run = _structured_context(organization, actor, cancellation=lambda: requested["cancelled"])
    requested["cancelled"] = True

    with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
        AcademicCatalogPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_cancelled"
    assert Subject.objects.filter(organization=organization).count() == 0
    assert LegacyImportBatch.objects.filter(run=run, source_table="lessons").count() == 0
