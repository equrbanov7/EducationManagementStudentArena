"""Sintetik miqyas profili (pytest ilə YIĞILMIR: ``python_files=bench_*.py`` lazımdır).

Qaçır::

    pytest apps/legacy_import/tests/bench_journal_scale.py \
        --override-ini python_files=bench_*.py --override-ini python_functions=bench_*
"""

import cProfile
import datetime
import io
import pstats
import time
from dataclasses import replace

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun
from apps.legacy_import.services.field_contracts import (
    ALLOWED_QB_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    SEMESTR_JURNAL_FIELDS,
    YEKUN_FIELDS,
)
from apps.legacy_import.services.ledger import create_run, start_run, upsert_entity_map
from apps.legacy_import.services.rehearsal_authorizer import (
    COURSE_OFFERING_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_bulk_target_validators,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from apps.legacy_import.services.rehearsal_journal_enrollments_phase import JournalEnrollmentsPhase
from apps.legacy_import.services.rehearsal_journal_lessons_phase import JournalLessonsPhase
from apps.legacy_import.services.rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import AcademicPeriod, Membership, Organization, Role
from core.constants import AcademicPeriodType, OrganizationType

JOURNALS = 20
STUDENTS = 25
LESSONS_PER_JOURNAL = 20

COLUMNS_BY_TABLE = {
    contract.source_table: contract.allowed_fields
    for contract in (
        SEMESTR_JURNAL_FIELDS,
        JOURNAL_FIELDS,
        JOURNAL_DATES_FIELDS,
        JOURNAL_POINT_FIELDS,
        JOURNAL_POINT_ARCHIVE_FIELDS,
        ALLOWED_QB_FIELDS,
        YEKUN_FIELDS,
    )
}
PHASE_KEYS = (
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
    "journal_marks",
    "journal_components",
    "journal_entry_scores",
    "journal_finals",
    "journal_lock",
    "journal_reconcile",
)


class FakeCursor:
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


class FakeSourceConnection:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table

    def server_is_read_only(self):
        return True

    def begin_read_only_snapshot(self):
        return None

    def session_is_read_only(self):
        return True

    def discover_table(self, source_table):
        return LegacyDiscoveredTable(
            source_table=source_table, column_names=COLUMNS_BY_TABLE[source_table], primary_key_fields=("id",)
        )

    def open_compiled_select(self, query):
        field_names = query.projection.field_names
        rows = self.rows_by_table.get(query.projection.source_table, [])
        return FakeCursor(
            tuple((name, None, None, None, None, None, None) for name in field_names),
            [tuple(row[name] for name in field_names) for row in rows],
        )

    def rollback(self):
        return None

    def close(self):
        return None


def factory(rows_by_table):
    def build():
        return FakeSourceConnection(rows_by_table)

    return build


def allow(**_kwargs):
    return True


def policy(**overrides):
    values = {
        "phase_keys": PHASE_KEYS,
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


def plan(rows_by_table):
    canonical = load_legacy_table_plan()
    return LegacyTablePlan(
        version=canonical.version,
        fingerprint=canonical.fingerprint,
        source_snapshot_sha256=canonical.source_snapshot_sha256,
        expected_row_count=sum(len(rows) for rows in rows_by_table.values()),
        entries=tuple(
            replace(canonical.entry_for(table), expected_rows=len(rows)) for table, rows in rows_by_table.items()
        ),
    )


def uniqid_for(index):
    return f"jrn{index:07d}"


def build_rows():
    journals = []
    dates = []
    students_json = "[" + ",".join(f'"{40 + s}"' for s in range(STUDENTS)) + "]"
    dates_pk = 0
    for index in range(JOURNALS):
        journals.append(
            {
                "id": index + 1,
                "uniqid": uniqid_for(index),
                "lesson_id": 64,
                "semestr": 1,
                "groups_id": '["2"]',
                "students_id": students_json,
                "teacher_id": 17,
                "fake": 0,
                "sonra_sil": 0,
                "fenn_saati": 60,
                "active": 1,
            }
        )
        for slot in range(LESSONS_PER_JOURNAL):
            dates_pk += 1
            dates.append(
                {
                    "id": dates_pk,
                    "journal_id": index + 1,
                    "month": 12,
                    "day": 1 + (slot % 28),
                    "time": f"{8 + (slot % 10):02d}:00",
                }
            )
    semesters = [{"id": 1, "name": "2021/2022 Payız", "type": "autumn", "is_current": "0"}]
    points = []
    point_pk = 0
    for index in range(JOURNALS):
        for slot in range(LESSONS_PER_JOURNAL):
            for student in range(STUDENTS):
                point_pk += 1
                points.append(
                    {
                        "id": point_pk,
                        "journal_uniqid": uniqid_for(index),
                        "month_id": "12",
                        "day_number": str(1 + (slot % 28)),
                        "student_id": 40 + student,
                        "point": "ie" if (point_pk % 3) else "7",
                        "added_date": datetime.datetime(2022, 4, 1, 9, 0, 0),
                        "time": datetime.timedelta(hours=8 + (slot % 10)),
                        "excusable": 0,
                        "why": "",
                        "j_id": index + 1,
                        "lab": 0,
                        "description": None,
                        "update_counter": 0,
                        "updated_at": None,
                    }
                )
    return {
        SEMESTR_JURNAL_FIELDS.source_table: semesters,
        JOURNAL_FIELDS.source_table: journals,
        JOURNAL_DATES_FIELDS.source_table: dates,
        JOURNAL_POINT_FIELDS.source_table: points,
        JOURNAL_POINT_ARCHIVE_FIELDS.source_table: [],
        ALLOWED_QB_FIELDS.source_table: [],
        YEKUN_FIELDS.source_table: [],
    }


@pytest.fixture()
def scale_env(db, django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="bench_actor", email="bench@example.test", password="test-only"
    )
    org = Organization.objects.create(
        name="Bench",
        slug="bench-org",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    rows_by_table = build_rows()
    table_plan = plan(rows_by_table)
    run = create_run(
        actor=actor,
        authorize=allow,
        organization=org,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=table_plan.source_snapshot_sha256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=table_plan.expected_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{table_plan.fingerprint[:12]}",
        transform_version=policy().transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    run = start_run(run_id=run.pk, actor=actor, authorize=allow)

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=org, code="MYEDU-64", name="Fənn", ects=5
    )
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 15),
        end_date=datetime.date(2022, 1, 31),
    )
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    validators = build_target_validators()
    for index in range(JOURNALS):
        offering = offering_model.objects.create(
            organization=org, subject=subject, period=period, lesson_hours=0, is_active=True
        )
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=allow,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            legacy_pk=uniqid_for(index),
            source_row_hash="a" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=COURSE_OFFERING_MODEL_LABEL,
            target_pk=str(offering.pk),
            target_validators=validators,
        )

    role, _created = Role.objects.get_or_create(
        organization=org, name="student", defaults={"display_name": "Student", "level": 50, "permissions": []}
    )
    Role.objects.filter(pk=role.pk).update(is_active=True)
    user_model = get_user_model()
    for index in range(STUDENTS):
        legacy = 40 + index
        student = user_model.objects.create(username=f"myedu.student.{legacy}", email="")
        profile = student.profile
        profile.organization = org
        profile.save(update_fields=["organization"])
        Membership.objects.create(organization=org, user=student, role=role, is_active=True)
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=allow,
            entity_type="student",
            legacy_pk=str(legacy),
            source_row_hash="b" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
            target_pk=str(student.pk),
            target_validators=validators,
        )

    return RehearsalContext(
        run_id=run.pk,
        organization=org,
        actor=actor,
        authorize=allow,
        target_validators=validators,
        policy=policy(),
        plan=table_plan,
        source_connection_factory=factory(rows_by_table),
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=lambda: False,
        stdout_note=lambda note: None,
        bulk_target_validators=build_bulk_target_validators(),
    )


class _Counter:
    def __init__(self):
        self.total = 0
        self.by_kind = {}

    def __call__(self, execute, sql, params, many, context):
        self.total += 1
        head = " ".join(sql.split()[:3])
        self.by_kind[head] = self.by_kind.get(head, 0) + 1
        return execute(sql, params, many)


def _measure(label, phase, context, rows):
    counter = _Counter()
    with connection.execute_wrapper(counter):
        started = time.perf_counter()
        report = phase.run(context)
        elapsed = time.perf_counter() - started
    queries = counter.total
    print(
        f"\n[{label}] rows={rows} elapsed={elapsed:.2f}s "
        f"rate={rows / elapsed:.1f} rows/s queries={queries} q/row={queries / rows:.1f}"
    )
    print(f"[{label}] state_counts={report.state_counts} digest={report.phase_digest[:16]}")
    for head, count in sorted(counter.by_kind.items(), key=lambda item: -item[1])[:30]:
        print(f"[{label}]   {count:>7}  {head}")
    return report, elapsed, queries


def _profile(label, phase, context, rows):
    profiler = cProfile.Profile()
    profiler.enable()
    _measure(label, phase, context, rows)
    profiler.disable()
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats("legacy_import|registrar|ledger", 30)
    print(stream.getvalue())


def bench_j2_enrollments(scale_env):
    _profile("J2", JournalEnrollmentsPhase(), scale_env, JOURNALS * STUDENTS)


def bench_j3_lessons(scale_env):
    JournalEnrollmentsPhase().run(scale_env)
    _profile("J3", JournalLessonsPhase(), scale_env, JOURNALS * LESSONS_PER_JOURNAL)


def bench_j4_marks(scale_env):
    from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase

    JournalEnrollmentsPhase().run(scale_env)
    JournalLessonsPhase().run(scale_env)
    _profile("J4", JournalMarksPhase(), scale_env, JOURNALS * STUDENTS * LESSONS_PER_JOURNAL)


@pytest.fixture()
def j1_env(db, django_user_model):
    """J1 girişləri: fənn/dövr/qrup/müəllim xəritələri (açılış HƏLƏ YOXDUR)."""

    from apps.organizations.models import OrgUnit

    actor = django_user_model.objects.create_superuser(
        username="bench_j1_actor", email="bench-j1@example.test", password="test-only"
    )
    org = Organization.objects.create(
        name="Bench J1",
        slug="bench-j1",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    rows_by_table = build_rows()
    for index, journal in enumerate(rows_by_table[JOURNAL_FIELDS.source_table]):
        journal["groups_id"] = f'["{2 + index}"]'
    table_plan = plan(rows_by_table)
    run = create_run(
        actor=actor,
        authorize=allow,
        organization=org,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=table_plan.source_snapshot_sha256,
        snapshot_size_bytes=2_142_912_818,
        source_row_count=table_plan.expected_row_count,
        schema_version=f"{TABLE_PLAN_VERSION}.{table_plan.fingerprint[:12]}",
        transform_version=policy().transform_version(),
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    run = start_run(run_id=run.pk, actor=actor, authorize=allow)
    validators = build_target_validators()

    def seed(entity_type, legacy_pk, label, target_pk):
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=allow,
            entity_type=entity_type,
            legacy_pk=str(legacy_pk),
            source_row_hash="c" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=label,
            target_pk=str(target_pk),
            target_validators=validators,
        )

    subject = django_apps.get_model("registrar", "Subject").objects.create(
        organization=org, code="MYEDU-64", name="Fənn", ects=5
    )
    seed("lesson_subject", 64, "registrar.subject", subject.pk)
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        academic_year="2021/2022",
        period_type=AcademicPeriodType.SEMESTER,
        start_date=datetime.date(2021, 9, 15),
        end_date=datetime.date(2022, 1, 31),
    )
    seed("academic_period", 1, "organizations.academicperiod", period.pk)
    for index in range(JOURNALS):
        unit = OrgUnit.objects.create(organization=org, name=f"Qrup {index}", unit_type="group")
        seed("group_unit", 2 + index, "organizations.orgunit", unit.pk)

    return RehearsalContext(
        run_id=run.pk,
        organization=org,
        actor=actor,
        authorize=allow,
        target_validators=validators,
        policy=policy(),
        plan=table_plan,
        source_connection_factory=factory(rows_by_table),
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=lambda: False,
        stdout_note=lambda note: None,
        bulk_target_validators=build_bulk_target_validators(),
    )


def bench_j1_offerings(j1_env):
    from apps.legacy_import.services.rehearsal_journal_offerings_phase import JournalOfferingsPhase

    _profile("J1", JournalOfferingsPhase(), j1_env, JOURNALS)
