"""Phase ``academic_catalog`` source tests: streams, parsing and derivation.

Nothing here touches the database: ``build_catalog_cohort`` is a pure function of
the four projected tables, which is exactly the property that lets the phase
module trust the cohort it is handed.
"""

from dataclasses import replace

import pytest

from apps.legacy_import.services import rehearsal_catalog_source as source_module
from apps.legacy_import.services.field_contracts import (
    CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    LESSON_CATALOG_FIELDS,
)
from apps.legacy_import.services.pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from apps.legacy_import.services.rehearsal_catalog_source import (
    build_catalog_cohort,
    lesson_references,
    plan_elective,
    semester_number,
)
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    PlanSemesterScheme,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

_CONTRACTS = {
    "lessons": LESSON_CATALOG_FIELDS,
    "curricula": CURRICULUM_CATALOG_FIELDS,
    "curricula_plan": CURRICULUM_PLAN_FIELDS,
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


def _plan(*, lessons=0, curricula=0, curricula_plan=0, groups=0):
    canonical = load_legacy_table_plan()
    counts = {"lessons": lessons, "curricula": curricula, "curricula_plan": curricula_plan, "groups": groups}
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


def _context(*, plan, factory, policy=None, cancelled=False):
    return RehearsalContext(
        run_id=None,
        organization=None,
        actor=None,
        authorize=lambda **_kwargs: True,
        target_validators={},
        policy=policy or _policy(),
        plan=plan,
        source_connection_factory=factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=lambda: cancelled,
        stdout_note=[].append,
    )


# ---------------------------------------------------------------------------
# V-8/V-14: ``curricula_plan.lesson_id`` is a JSON array, and it EXPANDS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "references", "rule_codes"),
    [
        ('["100"]', (100,), ()),
        ('["14"]', (14,), ()),
        ("[100]", (100,), ()),
        ('[ "7" ]', (7,), ()),
        # V-14: 26% of the live rows carry more than one element.
        ('["1","2"]', (1, 2), ("legacy_plan_lesson_reference_expanded",)),
        ('["9","9999"]', (9, 9999), ("legacy_plan_lesson_reference_expanded",)),
        # A repeated element is one reference, so it is not an "expansion".
        ('["5","5"]', (5,), ()),
        ("[]", (), ("legacy_plan_lesson_reference_invalid",)),
        ("", (), ("legacy_plan_lesson_reference_invalid",)),
        (None, (), ("legacy_plan_lesson_reference_invalid",)),
        ("100", (), ("legacy_plan_lesson_reference_invalid",)),
        ('{"a":1}', (), ("legacy_plan_lesson_reference_invalid",)),
        ('["abc"]', (), ("legacy_plan_lesson_reference_invalid",)),
        ('["1"', (), ("legacy_plan_lesson_reference_invalid",)),
        ("[0]", (), ("legacy_plan_lesson_reference_invalid",)),
        ("[true]", (), ("legacy_plan_lesson_reference_invalid",)),
        # A malformed sibling degrades the row; it never kills the reference.
        ('["1","abc"]', (1,), ("legacy_plan_lesson_reference_invalid",)),
    ],
)
def test_lesson_reference_matrix(raw, references, rule_codes):
    assert lesson_references(raw) == (references, rule_codes)


def test_a_250_character_blob_is_an_invalid_reference():
    blob = "x" * 250

    assert lesson_references(blob) == ((), ("legacy_plan_lesson_reference_invalid",))


# ---------------------------------------------------------------------------
# V-10/V-13: the semester scheme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "ordinal", "term_pair"),
    [
        ("payiz_1", (1, ()), (1, ())),
        ("yaz_1", (1, ("legacy_plan_semester_scheme_conflict",)), (2, ())),
        ("PAYIZ_3", (3, ()), (5, ())),
        (" yaz_7 ", (7, ("legacy_plan_semester_scheme_conflict",)), (14, ())),
        # V-13: ``payiz`` is odd and ``yaz`` even, so this row contradicts the
        # ORDINAL reading — and still migrates.
        ("payiz_2", (2, ("legacy_plan_semester_scheme_conflict",)), (3, ())),
        ("yaz_2", (2, ()), (4, ())),
        ("payiz_99", (0, ("legacy_plan_semester_out_of_range",)), (0, ("legacy_plan_semester_out_of_range",))),
        ("payiz_9", (9, ()), (0, ("legacy_plan_semester_out_of_range",))),
        ("", (0, ("legacy_plan_semester_invalid",)), (0, ("legacy_plan_semester_invalid",))),
        (None, (0, ("legacy_plan_semester_invalid",)), (0, ("legacy_plan_semester_invalid",))),
        ("guz_1", (0, ("legacy_plan_semester_invalid",)), (0, ("legacy_plan_semester_invalid",))),
        ("payiz_0", (0, ("legacy_plan_semester_out_of_range",)), (0, ("legacy_plan_semester_out_of_range",))),
    ],
)
def test_semester_matrix_under_both_schemes(raw, ordinal, term_pair):
    assert semester_number(raw, PlanSemesterScheme.ORDINAL) == ordinal
    assert semester_number(raw, PlanSemesterScheme.TERM_PAIR) == term_pair


def test_the_scheme_is_read_from_the_policy():
    factory = _factory({"curricula_plan": [_plan_row_values(1, semestr="payiz_3")]})
    plan = _plan(curricula_plan=1)

    ordinal = build_catalog_cohort(_context(plan=plan, factory=factory))
    paired = build_catalog_cohort(
        _context(
            plan=plan,
            factory=_factory({"curricula_plan": [_plan_row_values(1, semestr="payiz_3")]}),
            policy=_policy(plan_semester_scheme=PlanSemesterScheme.TERM_PAIR),
        )
    )

    assert ordinal.plan_rows[0].semester_number == 3
    assert paired.plan_rows[0].semester_number == 5


# ---------------------------------------------------------------------------
# Primary-key interlocks (copied verbatim from the structure phase)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("legacy_pk", ["7421", 7421.0, True, None])
def test_cohort_stream_rejects_non_integer_pk(legacy_pk):
    context = _context(plan=_plan(lessons=1), factory=_factory({"lessons": [_row(LESSON_CATALOG_FIELDS, legacy_pk)]}))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_type_drift"


@pytest.mark.parametrize("legacy_pk", [0, -1, MAX_LEDGER_PRIMARY_KEY + 1])
def test_cohort_stream_rejects_out_of_range_pk(legacy_pk):
    context = _context(plan=_plan(lessons=1), factory=_factory({"lessons": [_row(LESSON_CATALOG_FIELDS, legacy_pk)]}))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_out_of_range"


def test_cohort_stream_rejects_descending_pk():
    context = _context(
        plan=_plan(lessons=2),
        factory=_factory({"lessons": [_row(LESSON_CATALOG_FIELDS, 7), _row(LESSON_CATALOG_FIELDS, 3)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_pk_order_invalid"


@pytest.mark.parametrize("observed_rows", [1, 3])
def test_cohort_row_count_must_equal_plan_expected_rows(observed_rows):
    context = _context(
        plan=_plan(lessons=2),
        factory=_factory({"lessons": [_row(LESSON_CATALOG_FIELDS, index) for index in range(1, observed_rows + 1)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_row_count_mismatch"


def test_cohort_refuses_a_table_larger_than_the_bounded_cap():
    context = _context(plan=_plan(curricula_plan=source_module.CATALOG_COHORT_MAX_ROWS + 1), factory=_factory({}))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_cohort_too_large"


@pytest.mark.parametrize(
    ("table", "row"),
    [
        ("lessons", {"only_az": "0"}),
        ("curricula", {"speciality_id": "10"}),
        ("curricula_plan", {"kredit": 3}),
        ("curricula_plan", {"saat_muh": "30"}),
    ],
)
def test_a_non_numeric_legacy_column_fails_closed(table, row):
    context = _context(
        plan=_plan(**{table: 1}),
        factory=_factory({table: [_row(_CONTRACTS[table], 1, **row)]}),
    )

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        build_catalog_cohort(context)

    assert exc_info.value.code == "legacy_rehearsal_source_value_type_unsupported"


# ---------------------------------------------------------------------------
# The shared fixture: 5 lessons · 2 curricula · 5 plan rows · 3 groups
# ---------------------------------------------------------------------------


def _lesson_values(legacy_pk, **overrides):
    values = {"name": f"Fənn {legacy_pk}", "lesson_code": "37", "type": "1", "department_id": 3, "only_az": 0}
    values.update(overrides)
    return _row(LESSON_CATALOG_FIELDS, legacy_pk, **values)


def _plan_row_values(legacy_pk, **overrides):
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


def _curriculum_values(legacy_pk, **overrides):
    values = {
        "speciality_id": 10,
        "from_date": "",
        "to_date": "2023",
        "eyani_qiyabi": "Əyani",
        "bak_or_mag": "bak",
    }
    values.update(overrides)
    return _row(CURRICULUM_CATALOG_FIELDS, legacy_pk, **values)


def _group_values(legacy_pk, **overrides):
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


def _fixture_rows():
    return {
        "lessons": [
            _lesson_values(1, name="Riyaziyyat"),
            _lesson_values(2, name="  RIYAZIYYAT  "),
            _lesson_values(3, name="Fizika"),
            _lesson_values(4, name=""),
            _lesson_values(5, name="", department_id=4),
        ],
        "curricula": [
            _curriculum_values(100),
            _curriculum_values(101, from_date="2015", to_date=""),
        ],
        "curricula_plan": [
            _plan_row_values(1, lesson_id='["1"]', kredit=6.0),
            _plan_row_values(2, lesson_id='["3"]', kredit=4.0, semestr="yaz_2"),
            _plan_row_values(3, lesson_id='["3"]', kredit=5.0, semestr="payiz_3"),
            _plan_row_values(4, lesson_id='["4"]', kredit=0.0, semestr="payiz_1"),
            _plan_row_values(5, lesson_id='["1","3"]', kredit=2.5, semestr="yaz_2"),
        ],
        "groups": [
            _group_values(20, start_year=2021),
            _group_values(21, start_year=2019),
            _group_values(22, start_year=2020, curricula_id=0),
        ],
    }


def _fixture_cohort(**policy_overrides):
    return build_catalog_cohort(
        _context(
            plan=_plan(lessons=5, curricula=2, curricula_plan=5, groups=3),
            factory=_factory(_fixture_rows()),
            policy=_policy(**policy_overrides),
        )
    )


def test_credential_columns_never_reach_the_cohort():
    factory = _factory(_fixture_rows())

    build_catalog_cohort(
        _context(plan=_plan(lessons=5, curricula=2, curricula_plan=5, groups=3), factory=factory),
    )

    statements = [statement for connection in factory.connections for statement in connection.statements]
    assert len(statements) == 4  # lessons, curricula, curricula_plan and the groups re-read
    assert all("password" not in statement for statement in statements)
    assert all(connection.rolled_back and connection.closed for connection in factory.connections)


def test_subject_dedup_groups_by_name_and_department():
    cohort = _fixture_cohort()

    # 1 and 2 are the same name in the same department; 4 and 5 are BLANK names,
    # which must never dedup with each other (E-4).
    assert dict(cohort.subject_owner) == {1: 1, 2: 1, 3: 3, 4: 4, 5: 5}
    assert [(plan.legacy_pk, plan.code, plan.name) for plan in cohort.subjects] == [
        (1, "MYEDU-L1", "Riyaziyyat"),
        (3, "MYEDU-L3", "Fizika"),
        (4, "MYEDU-L4", "Fənn 4"),
        (5, "MYEDU-L5", "Fənn 5"),
    ]
    assert cohort.lessons[3].rule_codes == ("legacy_subject_name_blank",)


def test_ects_derivation_is_unique_empty_or_ambiguous():
    cohort = _fixture_cohort()
    by_pk = {plan.legacy_pk: plan for plan in cohort.subjects}

    assert (by_pk[1].ects, by_pk[1].rule_codes) == (6, ())
    # 4.0 and 5.0 are both acceptable, so the catalogue refuses to pick one.
    assert (by_pk[3].ects, by_pk[3].rule_codes) == (5, ("legacy_subject_ects_ambiguous",))
    # V-16: ``kredit == 0`` is the "not recorded" sentinel, not a bad value.
    assert (by_pk[4].ects, by_pk[4].rule_codes) == (5, ("legacy_subject_ects_unavailable",))
    assert (by_pk[5].ects, by_pk[5].rule_codes) == (5, ("legacy_subject_ects_unavailable",))


@pytest.mark.parametrize(
    ("kredit", "credit_ects", "rule_codes"),
    [
        (3.0, 3, ()),
        (60.0, 60, ()),
        (2.5, 0, ("legacy_plan_credit_unsupported",)),
        (0.0, 0, ()),  # V-16
        (None, 0, ()),
        (61.0, 0, ("legacy_plan_credit_unsupported",)),
        (-1.0, 0, ("legacy_plan_credit_unsupported",)),
    ],
)
def test_credit_matrix(kredit, credit_ects, rule_codes):
    cohort = build_catalog_cohort(
        _context(
            plan=_plan(curricula_plan=1), factory=_factory({"curricula_plan": [_plan_row_values(1, kredit=kredit)]})
        )
    )

    row = cohort.plan_rows[0]
    assert row.credit_ects == credit_ects
    assert [code for code in row.rule_codes if code.startswith("legacy_plan_credit")] == list(rule_codes)


def test_plan_row_classification_and_ranks():
    cohort = _fixture_cohort()
    by_pk = {row.legacy_pk: row for row in cohort.plan_rows}

    assert by_pk[1].semester_number == 1 and by_pk[1].order == 0
    assert by_pk[4].semester_number == 1 and by_pk[4].order == 1  # same (curriculum, semester)
    assert by_pk[2].semester_number == 2 and by_pk[2].order == 0
    assert by_pk[5].semester_number == 2 and by_pk[5].order == 1
    assert by_pk[3].semester_number == 3 and by_pk[3].order == 0
    assert by_pk[5].lesson_legacy_pks == (1, 3)
    assert "legacy_plan_lesson_reference_expanded" in by_pk[5].rule_codes
    # V-21: ``3`` is a ministry (mandatory) subject, so it is mapped, not unmapped.
    assert by_pk[1].type_token == "3" and "legacy_plan_type_unmapped" not in by_pk[1].rule_codes
    assert (by_pk[1].is_elective, by_pk[1].elective_group) == (False, "")
    assert by_pk[1].credit_text == "6.0000"
    assert by_pk[1].hours_token == "0.00|0.00|0.00|0.00|0.00|0.00"


def test_unmodelled_hours_and_prerequisites_are_recorded_not_written():
    cohort = build_catalog_cohort(
        _context(
            plan=_plan(curricula_plan=1),
            factory=_factory({"curricula_plan": [_plan_row_values(1, saat_muh=30.0, lesson_before_id=7)]}),
        )
    )

    row = cohort.plan_rows[0]
    assert row.prerequisite_legacy_pk == 7
    assert row.hours_token == "0.00|0.00|30.00|0.00|0.00|0.00"
    assert {"legacy_plan_hours_not_modelled", "legacy_plan_prerequisite_not_modelled"} <= set(row.rule_codes)


def test_curriculum_admission_year_prefers_from_date_then_the_groups_minimum():
    cohort = _fixture_cohort()
    by_pk = {curriculum.legacy_pk: curriculum for curriculum in cohort.curricula}

    # V-7: ``from_date`` is empty in the live dump, so 100 falls back to the
    # MIN of its groups' start years (2019, not the 2021 of the first group).
    assert (by_pk[100].admission_year, by_pk[100].admission_year_source) == (2019, "group")
    assert by_pk[100].rule_codes == ("legacy_curriculum_education_form_not_modelled",)
    assert (by_pk[101].admission_year, by_pk[101].admission_year_source) == (2015, "curriculum")
    assert by_pk[100].degree_level == "bachelor" and by_pk[100].education_form == "full_time"


def _year_rules(curriculum):
    """Only the ladder's own codes; the education-form note is always present."""

    return tuple(code for code in curriculum.rule_codes if "admission_year" in code)


@pytest.mark.parametrize(
    ("from_date", "to_date", "bak_or_mag", "start_year", "curricula_id", "expected"),
    [
        # T1 outranks everything below it …
        ("2018", "2026", "bak", 2019, 100, (2018, "curriculum", ())),
        # … but a year outside 1950..2100 fails the tier closed instead of passing.
        ("1800", "2026", "bak", 2019, 100, (2019, "group", ())),
        # T2: the MIN of the referencing groups, before any inference is made.
        ("", "2026", "bak", 2019, 100, (2019, "group", ())),
        # T3 (V-20): ``to_date`` minus the degree's nominal duration — bakalavr 4 …
        ("", "2026", "bak", 0, 100, (2022, "to_date_minus_duration", ("legacy_curriculum_admission_year_inferred",))),
        # … magistr 2, so the SAME ``to_date`` yields a different intake year.
        ("", "2026", "mag", 0, 100, (2024, "to_date_minus_duration", ("legacy_curriculum_admission_year_inferred",))),
        ("", "2029", "bak", 0, 100, (2025, "to_date_minus_duration", ("legacy_curriculum_admission_year_inferred",))),
        # A ``to_date`` that is not a bare four-digit year is no year at all …
        ("", "20xx", "bak", 0, 100, (None, "none", ("legacy_curriculum_admission_year_unresolved",))),
        ("", "", "bak", 0, 100, (None, "none", ("legacy_curriculum_admission_year_unresolved",))),
        # … and neither is one whose arithmetic leaves the window (1953 − 4).
        ("", "1953", "bak", 0, 100, (None, "none", ("legacy_curriculum_admission_year_unresolved",))),
        # The group points at no curriculum, so T2 has nothing to contribute.
        ("", "", "bak", 2019, 0, (None, "none", ("legacy_curriculum_admission_year_unresolved",))),
        ("", "", "bak", 1800, 100, (None, "none", ("legacy_curriculum_admission_year_unresolved",))),
    ],
)
def test_curriculum_year_ladder(from_date, to_date, bak_or_mag, start_year, curricula_id, expected):
    cohort = build_catalog_cohort(
        _context(
            plan=_plan(curricula=1, groups=1),
            factory=_factory(
                {
                    "curricula": [_curriculum_values(100, from_date=from_date, to_date=to_date, bak_or_mag=bak_or_mag)],
                    "groups": [_group_values(20, start_year=start_year, curricula_id=curricula_id)],
                }
            ),
        )
    )

    curriculum = cohort.curricula[0]
    # A one-row cohort has no DATED neighbour, so T4 cannot rescue it: the tail of
    # this ladder is still the old quarantine path.
    assert (curriculum.admission_year, curriculum.admission_year_source) == expected[:2]
    assert _year_rules(curriculum) == expected[2]


@pytest.mark.parametrize(
    ("undated_pk", "expected_year"),
    [
        # The largest DATED id BELOW the undated one wins …
        (102, 2018),
        # … and only when there is none does the smallest dated id above answer.
        (99, 2016),
    ],
)
def test_undated_curriculum_adopts_its_nearest_dated_neighbour(undated_pk, expected_year):
    rows = sorted(
        [
            _curriculum_values(100, from_date="2016", to_date=""),
            _curriculum_values(101, from_date="2018", to_date=""),
            _curriculum_values(undated_pk, from_date="", to_date=""),
        ],
        key=lambda row: row["id"],
    )

    cohort = build_catalog_cohort(
        _context(plan=_plan(curricula=3), factory=_factory({"curricula": rows})),
    )

    adopted = next(item for item in cohort.curricula if item.legacy_pk == undated_pk)
    assert (adopted.admission_year, adopted.admission_year_source) == (expected_year, "neighbor")
    assert _year_rules(adopted) == ("legacy_curriculum_admission_year_neighbor",)
    # The dated rows keep their own source token: T4 only fills the gaps.
    assert [item.admission_year_source for item in cohort.curricula if item.legacy_pk in (100, 101)] == [
        "curriculum",
        "curriculum",
    ]


def test_the_neighbour_tier_is_deterministic_across_builds():
    rows = [
        _curriculum_values(100, from_date="", to_date=""),
        _curriculum_values(101, from_date="2016", to_date=""),
        _curriculum_values(102, from_date="", to_date=""),
        _curriculum_values(103, from_date="2020", to_date=""),
        _curriculum_values(104, from_date="", to_date=""),
    ]

    first = build_catalog_cohort(_context(plan=_plan(curricula=5), factory=_factory({"curricula": rows})))
    second = build_catalog_cohort(_context(plan=_plan(curricula=5), factory=_factory({"curricula": rows})))

    assert first.curricula == second.curricula
    assert [(item.legacy_pk, item.admission_year, item.admission_year_source) for item in first.curricula] == [
        (100, 2016, "neighbor"),  # nothing dated below ⇒ the smallest dated above
        (101, 2016, "curriculum"),
        (102, 2016, "neighbor"),  # the largest dated id below is 101
        (103, 2020, "curriculum"),
        (104, 2020, "neighbor"),
    ]


def test_a_cohort_with_no_dated_curriculum_still_quarantines():
    rows = [
        _curriculum_values(100, from_date="", to_date=""),
        _curriculum_values(101, from_date="", to_date="20xx"),
    ]

    cohort = build_catalog_cohort(_context(plan=_plan(curricula=2), factory=_factory({"curricula": rows})))

    assert [(item.admission_year, item.admission_year_source) for item in cohort.curricula] == [
        (None, "none"),
        (None, "none"),
    ]
    assert all(_year_rules(item) == ("legacy_curriculum_admission_year_unresolved",) for item in cohort.curricula)


def test_the_inferred_tier_feeds_the_neighbour_tier():
    """T3's output is DATED, so T4 may legitimately spread an inference."""

    rows = [
        _curriculum_values(100, from_date="", to_date="2026", bak_or_mag="mag"),
        _curriculum_values(101, from_date="", to_date=""),
    ]

    cohort = build_catalog_cohort(_context(plan=_plan(curricula=2), factory=_factory({"curricula": rows})))

    assert [(item.admission_year, item.admission_year_source) for item in cohort.curricula] == [
        (2024, "to_date_minus_duration"),
        (2024, "neighbor"),
    ]


def test_an_unmapped_degree_defaults_to_bachelor():
    cohort = build_catalog_cohort(
        _context(
            plan=_plan(curricula=2),
            factory=_factory(
                {
                    "curricula": [
                        _curriculum_values(100, bak_or_mag="", eyani_qiyabi=""),
                        _curriculum_values(101, bak_or_mag="mag", eyani_qiyabi="Qiyabi"),
                    ]
                }
            ),
        )
    )

    assert cohort.curricula[0].degree_level == "bachelor"
    assert "legacy_curriculum_degree_defaulted" in cohort.curricula[0].rule_codes
    assert cohort.curricula[1].degree_level == "master"
    # V-20: the defaulted degree also picks the T3 duration, so the two rows read
    # the SAME ``to_date`` into two different intake years.
    assert (cohort.curricula[0].admission_year, cohort.curricula[1].admission_year) == (2019, 2021)
    assert cohort.curricula[1].rule_codes == (
        "legacy_curriculum_education_form_not_modelled",
        "legacy_curriculum_admission_year_inferred",
    )


# ---------------------------------------------------------------------------
# V-21: ``curricula_plan.type`` is an elective BLOCK label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        # The dotted families the live dump carries: 2.1/2.2 and 4.01…4.24.
        ("2.1", (True, "2.1", ("legacy_plan_elective_block",))),
        ("2.2", (True, "2.2", ("legacy_plan_elective_block",))),
        ("4.01", (True, "4.01", ("legacy_plan_elective_block",))),
        ("4.07", (True, "4.07", ("legacy_plan_elective_block",))),
        ("4.24", (True, "4.24", ("legacy_plan_elective_block",))),
        # Ministry subjects: a bare integer, and the blank that means the same.
        ("1", (False, "", ())),
        ("3", (False, "", ())),
        ("5", (False, "", ())),
        ("6", (False, "", ())),
        ("8", (False, "", ())),
        ("", (False, "", ())),
        # Neither family ⇒ still visible, never mandatory-by-luck (zero expected).
        ("X.Y", (False, "", ("legacy_plan_type_unmapped",))),
        ("2.1.3", (False, "", ("legacy_plan_type_unmapped",))),
        ("2.", (False, "", ("legacy_plan_type_unmapped",))),
        (".1", (False, "", ("legacy_plan_type_unmapped",))),
        ("-1", (False, "", ("legacy_plan_type_unmapped",))),
        ("SEÇMƏ", (False, "", ("legacy_plan_type_unmapped",))),
    ],
)
def test_plan_elective_matrix(token, expected):
    assert plan_elective(token) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.07", (True, "4.07")),
        (" 4.07 ", (True, "4.07")),  # ``clean_code`` strips before the match runs
        ("3", (False, "")),
        ("", (False, "")),
        (None, (False, "")),
        ("x.y", (False, "")),
    ],
)
def test_the_elective_mapping_reaches_the_plan_row(raw, expected):
    cohort = build_catalog_cohort(
        _context(plan=_plan(curricula_plan=1), factory=_factory({"curricula_plan": [_plan_row_values(1, type=raw)]}))
    )

    row = cohort.plan_rows[0]
    assert (row.is_elective, row.elective_group) == expected


def test_one_elective_block_is_the_curriculum_semester_and_group_triple():
    """V-21: same (curriculum, semester, elective_group) ⇒ one block."""

    rows = [
        _plan_row_values(1, lesson_id='["1"]', type="4.01", semestr="payiz_1"),
        _plan_row_values(2, lesson_id='["3"]', type="4.01", semestr="payiz_1"),
        # A different semester is a different block even under the same label.
        _plan_row_values(3, lesson_id='["3"]', type="4.01", semestr="yaz_2"),
        _plan_row_values(4, lesson_id='["3"]', type="3", semestr="payiz_1"),
    ]

    cohort = build_catalog_cohort(_context(plan=_plan(curricula_plan=4), factory=_factory({"curricula_plan": rows})))

    blocks = {
        (row.curriculum_legacy_pk, row.semester_number, row.elective_group)
        for row in cohort.plan_rows
        if row.is_elective
    }
    assert blocks == {(100, 1, "4.01"), (100, 2, "4.01")}
    assert [row.legacy_pk for row in cohort.plan_rows if row.is_elective] == [1, 2, 3]
    assert cohort.plan_rows[3].elective_group == ""
