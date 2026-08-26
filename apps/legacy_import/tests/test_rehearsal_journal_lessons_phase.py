"""Phase ``journal_lessons`` (J3) testləri: il törəməsi, orphan, invalid, dedup."""

import datetime
import hashlib
from dataclasses import replace

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue, LegacyMigrationRun
from apps.legacy_import.services.field_contracts import (
    JOURNAL_DATES_FIELDS,
    JOURNAL_FIELDS,
    SEMESTR_JURNAL_FIELDS,
    is_credential_field,
)
from apps.legacy_import.services.ledger import create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    COURSE_OFFERING_MODEL_LABEL,
    LESSON_MODEL_LABEL,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
    encoded_part,
)
from apps.legacy_import.services.rehearsal_journal_lessons_phase import (
    DERIVED_DIGEST_NAMESPACE,
    JOURNAL_LESSONS_PHASE_KEY,
    JournalLessonsPhase,
    parse_lesson_schedule,
)
from apps.legacy_import.services.rehearsal_journal_lessons_targets import (
    ISSUE_SEVERITY,
    LESSON_ENTITY_TYPE,
    lesson_derivation_hash,
)
from apps.legacy_import.services.rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.organizations.models import AcademicPeriod, Organization
from core.constants import AcademicPeriodType, OrganizationType

_PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "worker_materialisation",
    "sar_materialisation",
    "journal_periods",
    "journal_offerings",
    "journal_enrollments",
    "journal_lessons",
)
_COLUMNS_BY_TABLE = {
    SEMESTR_JURNAL_FIELDS.source_table: SEMESTR_JURNAL_FIELDS.allowed_fields,
    JOURNAL_FIELDS.source_table: JOURNAL_FIELDS.allowed_fields,
    JOURNAL_DATES_FIELDS.source_table: JOURNAL_DATES_FIELDS.allowed_fields,
}


# ---------------------------------------------------------------------------
# Çox-cədvəlli fake source (J0/J1 fixture-lərinin birləşmiş forması)
# ---------------------------------------------------------------------------


class _FakeCursor:
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
        return LegacyDiscoveredTable(
            source_table=source_table,
            column_names=_COLUMNS_BY_TABLE[source_table],
            primary_key_fields=("id",),
        )

    def open_compiled_select(self, query):
        self.statements.append(query.mysql_statement())
        field_names = query.projection.field_names
        rows = self.rows_by_table.get(query.projection.source_table, [])
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


def _semester_row(legacy_pk=1, name="2021/2022 Payız", type_token="autumn", is_current="0"):
    return {"id": legacy_pk, "name": name, "type": type_token, "is_current": is_current}


def _journal_row(legacy_pk, uniqid, **overrides):
    values = {
        "id": legacy_pk,
        "uniqid": uniqid,
        "lesson_id": 64,
        "semestr": 1,
        "groups_id": '["2"]',
        "students_id": '["42","43"]',
        "teacher_id": 17,
        "fake": 0,
        "sonra_sil": 0,
        "active": 1,
    }
    values.update(overrides)
    return values


def _dates_row(legacy_pk, journal_id=2, month=12, day=30, time_value="14:00"):
    return {"id": legacy_pk, "journal_id": journal_id, "month": month, "day": day, "time": time_value}


def _tables(*, semesters=None, journals=None, dates=None):
    return {
        SEMESTR_JURNAL_FIELDS.source_table: list(semesters if semesters is not None else [_semester_row()]),
        JOURNAL_FIELDS.source_table: list(journals if journals is not None else [_journal_row(2, "rooBx39tsK")]),
        JOURNAL_DATES_FIELDS.source_table: list(dates if dates is not None else []),
    }


def _plan(rows_by_table):
    from apps.legacy_import.services.table_plan import LegacyTablePlan, load_legacy_table_plan

    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=sum(len(rows) for rows in rows_by_table.values()),
        entries=tuple(
            replace(canonical.entry_for(source_table), expected_rows=len(rows))
            for source_table, rows in rows_by_table.items()
        ),
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
        "max_staged_accounts": 0,
        "student_role_name": "",
        "worker_role_name": "",
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
# Saf forma / taksonomiya / parse (verilənlər bazasız)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_numeric_shape():
    phase = JournalLessonsPhase()

    assert phase.phase_key == JOURNAL_LESSONS_PHASE_KEY and phase.order == 38
    assert phase.source_tables == () and phase.entity_types == (LESSON_ENTITY_TYPE,)
    assert phase.declared_source_rows(_plan(_tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    # Açar rəqəmdir: rebuild-in DEFOLT ``int`` sıralaması stream sırası ilə eynidir.
    assert not hasattr(phase, "derived_ledger_sort_key")
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "lesson_materialised"
    assert phase.derived_state_key("skipped") == "lesson_skipped"
    assert phase.derived_state_key("quarantined") == "lesson_unresolved"


def test_issue_severity_map_covers_exactly_the_lesson_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_lesson_invalid": "warning",
        "legacy_journal_lesson_orphan": "info",
        "legacy_journal_lesson_duplicate": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)
    assert all(rule_code.startswith("legacy_journal_") for rule_code in ISSUE_SEVERITY)


def test_the_dates_contract_is_credential_free_and_default_deny():
    # Real sxem (DESCRIBE ilə təsdiqlənib): sem_muh və added_date QƏSDƏN kənarda.
    assert JOURNAL_DATES_FIELDS.allowed_fields == ("id", "journal_id", "month", "day", "time")
    assert not any(is_credential_field(field_name) for field_name in JOURNAL_DATES_FIELDS.allowed_fields)


@pytest.mark.parametrize(
    "month, day, time_value, expected",
    [
        # Ay 9-12 akademik ilin BİRİNCİ ilində, ay 1-8 İKİNCİ ilindədir.
        (12, 30, "14:00", (datetime.date(2021, 12, 30), datetime.time(14, 0))),
        (9, 15, "08:30", (datetime.date(2021, 9, 15), datetime.time(8, 30))),
        (2, 17, "13:30", (datetime.date(2022, 2, 17), datetime.time(13, 30))),
        (8, 31, "23:59", (datetime.date(2022, 8, 31), datetime.time(23, 59))),
        # 2021/2022 üçün fevralın 29-u yoxdur (2022 uzun il deyil).
        (2, 29, "10:00", None),
        (2, 30, "10:00", None),
        (0, 15, "10:00", None),
        (13, 15, "10:00", None),
        (11, 0, "10:00", None),
        (11, 32, "10:00", None),
        # Mənbədə real rast gəlinən pozuq saat formaları.
        (11, 16, "10:0_", None),
        (11, 16, "1_:__", None),
        (11, 16, "83:0_", None),
        (11, 16, "24:00", None),
        (11, 16, "9:00", None),
        (11, 16, None, None),
    ],
)
def test_parse_lesson_schedule_is_strict(month, day, time_value, expected):
    assert parse_lesson_schedule(first_year=2021, month=month, day=day, time_value=time_value) == expected


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalLessonsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [
        ("journal_lessons",),
        ("journal_periods", "journal_lessons"),
        ("journal_offerings", "journal_lessons"),
    ],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    tables = _tables()
    context = _context(plan=_plan(tables), factory=_factory(tables), policy=_policy(phase_keys=phase_keys))

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalLessonsPhase().run(context)

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_the_lesson_derivation_hash_follows_the_documented_recipe():
    digest = hashlib.sha256(b"legacy-rehearsal-journal-lesson-derivation-v1\x00")
    for part in (
        JOURNAL_DATES_FIELDS.fingerprint,
        "10",
        "b" * 64,
        "materialised",
        "2",
        "2021-12-30",
        "14:00",
    ):
        digest.update(encoded_part(part))

    computed = lesson_derivation_hash(
        legacy_pk=10,
        row_hash="b" * 64,
        outcome_token="materialised",
        journal_ref="2",
        date_text="2021-12-30",
        time_text="14:00",
    )

    assert computed == digest.hexdigest()
    assert computed != lesson_derivation_hash(
        legacy_pk=10,
        row_hash="b" * 64,
        outcome_token="duplicate",
        journal_ref="2",
        date_text="2021-12-30",
        time_text="14:00",
    )


# ---------------------------------------------------------------------------
# Ledger-li mühit
# ---------------------------------------------------------------------------


@pytest.fixture()
def lesson_actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_lessons_actor",
        email="journal-lessons-actor@example.test",
        password="test-only",
    )


def _organization(actor, slug):
    return Organization.objects.create(
        name=f"Journal {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )


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


def _make_offering(organization, *, instructor=None, code="MYEDU-64"):
    from django.apps import apps as django_apps

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=organization, code=code, name=f"Fənn {code}", ects=5
    )
    period = AcademicPeriod.objects.create(
        organization=organization,
        name=f"Payız {code}",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 15),
        end_date=datetime.date(2022, 1, 31),
    )
    return django_apps.get_model("registrar", "CourseOffering").objects.create(
        organization=organization, subject=subject, period=period, instructor=instructor, lesson_hours=0, is_active=True
    )


def _seed_offering_map(organization, actor, run_id, *, uniqids=("rooBx39tsK",), instructor=None):
    """J1-in qoyub getdiyi offering map-ları (hamısı eyni real offering-i göstərir)."""

    offering = _make_offering(organization, instructor=instructor)
    for uniqid in uniqids:
        upsert_entity_map(
            run_id=run_id,
            actor=actor,
            authorize=_allow,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            legacy_pk=uniqid,
            source_row_hash=_seed_hash(f"course_offering:{uniqid}"),
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=COURSE_OFFERING_MODEL_LABEL,
            target_pk=str(offering.pk),
            target_validators=build_target_validators(),
        )
    return offering


def _seeded_context(organization, actor, run, *, tables, policy=None, notes=None, cancelled=None):
    context = _context(
        plan=_plan(tables),
        factory=_factory(tables),
        policy=policy or _policy(),
        organization=organization,
        actor=actor,
        notes=notes,
        cancelled=cancelled,
    )
    return replace(context, run_id=run.pk)


def _states(run):
    return dict(
        run.entity_observations.filter(entity_map__entity_type=LESSON_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=LESSON_ENTITY_TYPE)
    }


def _lessons(organization):
    from django.apps import apps as django_apps

    return django_apps.get_model("registrar", "Lesson").objects.filter(organization=organization)


@pytest.mark.django_db
def test_the_happy_path_creates_the_lesson_with_the_derived_year(lesson_actor, django_user_model):
    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-primary")
    instructor = django_user_model.objects.create_user(username="myedu.worker.lessons.17", email="", password=None)
    tables = _tables(dates=[_dates_row(10, month=12, day=30, time_value="14:00")])
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    offering = _seed_offering_map(organization, actor, run.pk, instructor=instructor)
    notes = []

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables, notes=notes))

    assert dict(report.state_counts) == {"lesson_materialised": 1}
    assert _states(run) == {"10": "migrated"}
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_LESSONS_PHASE_KEY}.records.1"]
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    lesson = _lessons(organization).get()
    assert lesson.offering_id == offering.pk
    # Ay 12 → akademik ilin (2021/2022) birinci ili: 2021-12-30.
    assert lesson.date == datetime.date(2021, 12, 30)
    assert lesson.start_time == datetime.time(14, 0)
    # Spec J3 defoltları: kind=lecture, hours=2, instructor açılışın müəllimi.
    assert lesson.kind == "lecture"
    assert lesson.hours == 2
    assert lesson.instructor_id == instructor.pk
    assert lesson.created_by_id is None
    observation = run.entity_observations.get(entity_map__entity_type=LESSON_ENTITY_TYPE)
    assert observation.target_model_label == LESSON_MODEL_LABEL
    assert observation.target_pk == str(lesson.pk)


@pytest.mark.django_db
def test_a_spring_month_lands_in_the_second_academic_year(lesson_actor):
    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-spring")
    tables = _tables(dates=[_dates_row(10, month=2, day=17, time_value="13:30")])
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables))

    assert dict(report.state_counts) == {"lesson_materialised": 1}
    lesson = _lessons(organization).get()
    # Ay 2 → akademik ilin (2021/2022) İKİNCİ ili: 2022-02-17.
    assert lesson.date == datetime.date(2022, 2, 17)
    assert lesson.instructor_id is None  # açılışın müəllimi yoxdur → NULL güzgüsü


@pytest.mark.django_db
def test_orphan_rows_are_skipped_for_both_unknown_and_filtered_journals(lesson_actor):
    """Spec J3: jurnal tapılmır VƏ YA V6/karantinlə süzülüb → SKIPPED orphan."""

    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-orphan")
    tables = _tables(
        journals=[
            _journal_row(2, "rooBx39tsK"),
            _journal_row(3, "fakeAAAAAA", fake=1),  # J1 süzüb — offering map-ı yoxdur
        ],
        dates=[
            _dates_row(10, journal_id=999),  # heç bir jurnala bağlanmır (mənbədə 28 belə sətir var)
            _dates_row(11, journal_id=3),
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables))

    assert dict(report.state_counts) == {"lesson_skipped": 2}
    assert _states(run) == {"10": "skipped", "11": "skipped"}
    assert _issues(run) == {
        ("10", "legacy_journal_lesson_orphan"): "info",
        ("11", "legacy_journal_lesson_orphan"): "info",
    }
    assert _lessons(organization).count() == 0


@pytest.mark.django_db
def test_an_unbuildable_date_or_time_quarantines_the_row(lesson_actor):
    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-invalid")
    tables = _tables(
        dates=[
            _dates_row(10, month=2, day=30),  # 2022-02-30 mövcud deyil
            _dates_row(11, time_value="10:0_"),  # mənbədə real rast gəlinən forma
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables))

    assert dict(report.state_counts) == {"lesson_unresolved": 2}
    assert _states(run) == {"10": "quarantined", "11": "quarantined"}
    assert _issues(run) == {
        ("10", "legacy_journal_lesson_invalid"): "warning",
        ("11", "legacy_journal_lesson_invalid"): "warning",
    }
    assert _lessons(organization).count() == 0
    for observation in run.entity_observations.filter(entity_map__entity_type=LESSON_ENTITY_TYPE):
        assert observation.target_model_label == "" and observation.target_pk == ""


@pytest.mark.django_db
def test_a_repeated_slot_keeps_the_first_row_and_skips_the_rest(lesson_actor):
    """Mənbədəki 69,650 artıq slot sətrinin analoqu: ilk id udur, qalanları qeydli."""

    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-duplicate")
    tables = _tables(
        dates=[
            _dates_row(10, month=12, day=30, time_value="14:00"),
            _dates_row(11, month=12, day=30, time_value="14:00"),
            _dates_row(12, month=12, day=30, time_value="15:00"),  # fərqli saat — dublikat deyil
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables))

    assert dict(report.state_counts) == {"lesson_materialised": 2, "lesson_skipped": 1}
    assert _states(run) == {"10": "migrated", "11": "skipped", "12": "migrated"}
    assert _issues(run) == {("11", "legacy_journal_lesson_duplicate"): "info"}
    assert _lessons(organization).count() == 2


@pytest.mark.django_db
def test_merged_journals_fold_the_same_slot_into_one_lesson(lesson_actor):
    """V7 merge nəticəsi: eyni offering-ə qatlanan jurnalların eyni slotu tək dərsdir."""

    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-merge")
    tables = _tables(
        journals=[
            _journal_row(2, "firstAAAAA"),
            _journal_row(3, "secondBBBB"),
        ],
        dates=[
            _dates_row(10, journal_id=2, month=12, day=30, time_value="14:00"),
            _dates_row(11, journal_id=3, month=12, day=30, time_value="14:00"),
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk, uniqids=("firstAAAAA", "secondBBBB"))

    report = JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables))

    # Hər iki sətir MIGRATED-dir (öz jurnalının slotudur), amma hədəf TƏK dərsdir.
    assert dict(report.state_counts) == {"lesson_materialised": 2}
    assert _lessons(organization).count() == 1
    target_pks = set(
        run.entity_observations.filter(entity_map__entity_type=LESSON_ENTITY_TYPE).values_list("target_pk", flat=True)
    )
    assert len(target_pks) == 1


@pytest.mark.django_db
def test_a_repeated_invocation_replays_the_sealed_decisions(lesson_actor):
    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-replay")
    tables = _tables(
        dates=[
            _dates_row(10, month=12, day=30, time_value="14:00"),
            _dates_row(11, month=12, day=30, time_value="14:00"),
            _dates_row(12, journal_id=999),
            _dates_row(13, month=2, day=30),
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)
    phase = JournalLessonsPhase()

    first = phase.run(_seeded_context(organization, actor, run, tables=tables))
    second = phase.run(_seeded_context(organization, actor, run, tables=tables))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=LESSON_ENTITY_TYPE).count() == 4
    assert _lessons(organization).count() == 1


@pytest.mark.django_db
def test_the_live_phase_digest_equals_the_numeric_ledger_rebuild(lesson_actor):
    actor = lesson_actor
    organization = _organization(actor, "journal-lessons-rebuild")
    tables = _tables(
        dates=[
            _dates_row(10, month=12, day=30, time_value="14:00"),
            _dates_row(11, journal_id=999),
            _dates_row(12, month=2, day=30),
        ],
    )
    run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
    _seed_offering_map(organization, actor, run.pk)
    phase = JournalLessonsPhase()
    plan = _plan(tables)

    live = phase.run(_seeded_context(organization, actor, run, tables=tables))
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=plan)

    assert rebuilt.phase_digest == live.phase_digest
    assert (
        dict(rebuilt.state_counts)
        == dict(live.state_counts)
        == {"lesson_materialised": 1, "lesson_skipped": 1, "lesson_unresolved": 1}
    )
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()


@pytest.mark.django_db
def test_the_phase_digest_is_identical_across_two_independent_runs(lesson_actor):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    actor = lesson_actor
    tables = _tables(
        dates=[
            _dates_row(10, month=12, day=30, time_value="14:00"),
            _dates_row(11, month=12, day=30, time_value="14:00"),
            _dates_row(12, journal_id=999),
        ],
    )
    digests = []
    for slug in ("journal-lessons-run-a", "journal-lessons-run-b"):
        organization = _organization(actor, slug)
        run = _running_run(organization, actor, policy=_policy(), plan=_plan(tables))
        _seed_offering_map(organization, actor, run.pk)
        digests.append(JournalLessonsPhase().run(_seeded_context(organization, actor, run, tables=tables)).phase_digest)

    assert digests[0] == digests[1]
