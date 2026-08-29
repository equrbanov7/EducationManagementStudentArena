"""J4-J8 testləri üçün paylaşılan fake-source və ledger seed qatı.

Bu modul TEST yardımçısıdır (``test_`` prefiksi qəsdən yoxdur — pytest onu
kolleksiya etmir).  J0-J3 testlərindəki fake-source formasının davamıdır, sadəcə
yeddi cədvəli birdən daşıyır: ``semestr_jurnal``, ``journals``,
``journals_dates_added_by_teacher``, ``journals_dates_points``, onun arxivi,
``allowed_qb`` və ``yekun``.
"""

import datetime
import hashlib
from dataclasses import replace

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

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
from apps.legacy_import.services.legacy_grade_field_contracts import (
    EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS,
)
from apps.legacy_import.services.rehearsal_authorizer import (
    COURSE_OFFERING_MODEL_LABEL,
    ENROLLMENT_MODEL_LABEL,
    LESSON_MODEL_LABEL,
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
from apps.legacy_import.services.rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_journal_lessons_targets import LESSON_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from apps.legacy_import.services.source_extraction import LegacyDiscoveredTable
from apps.legacy_import.services.syllabus_field_contracts import (
    JOURNAL_SYLLABUS_FIELDS,
    SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS,
)
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, LegacyTablePlan, load_legacy_table_plan
from apps.organizations.models import AcademicPeriod, Membership, Organization, Role
from core.constants import AcademicPeriodType, OrganizationType

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
    "journal_selfwork",
    "journal_lock",
    "legacy_grade_facts",
    "journal_reconcile",
    "legacy_grade_artifacts",
)
UNIQID = "rooBx39tsK"
OTHER_UNIQID = "secondBBBB"
STUDENT_A = 42
STUDENT_B = 43
SYLLABUS_ID = 5
SYLLABUS_UNIQID = "sylBx39tsK"


def _discovered_columns(*contracts):
    """Bir cədvəlin DESCRIBE sütunları — ONA BAXAN BÜTÜN kontraktların birləşməsi.

    ``journals`` iki kontraktla oxunur (``JOURNAL_FIELDS`` və J9-un kiçik
    ``JOURNAL_SYLLABUS_FIELDS``-i), canlı ``DESCRIBE`` isə həmişə tam sütun
    dəstini verir — fake mənbə də eynisini etməlidir ki, proyeksiya qapısı
    real şəraiti sınasın."""

    columns: dict[str, tuple[str, ...]] = {}
    for contract in contracts:
        merged = list(columns.get(contract.source_table, ()))
        merged.extend(name for name in contract.allowed_fields if name not in merged)
        columns[contract.source_table] = tuple(merged)
    return columns


COLUMNS_BY_TABLE = _discovered_columns(
    SEMESTR_JURNAL_FIELDS,
    JOURNAL_FIELDS,
    JOURNAL_SYLLABUS_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_POINT_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    ALLOWED_QB_FIELDS,
    YEKUN_FIELDS,
    EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS,
    SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS,
)
# J-V7 kəsimindən əvvəl / sonra (2022-03-30).
BEFORE_CUTOFF = datetime.datetime(2022, 1, 5, 9, 0, 0)
AFTER_CUTOFF = datetime.datetime(2022, 6, 5, 9, 0, 0)
MAIN_ADDED = datetime.datetime(2022, 4, 1, 9, 0, 0)
# Defolt arqumentlərdə funksiya çağırışı olmasın deyə (flake8 B008) hamısı sabitdir.
DEFAULT_TIME = datetime.timedelta(hours=14)
DEFAULT_LESSON_SLOTS = (
    (10, datetime.date(2021, 12, 30), datetime.time(14, 0)),
    (11, datetime.date(2021, 12, 31), datetime.time(14, 0)),
)
DEFAULT_PERIOD_END = datetime.date(2022, 1, 31)


# ── fake source ──────────────────────────────────────────────────────────────


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
            column_names=COLUMNS_BY_TABLE[source_table],
            primary_key_fields=("id",),
        )

    def open_compiled_select(self, query):
        self.statements.append(query.mysql_statement())
        field_names = query.projection.field_names
        rows = self.rows_by_table.get(query.projection.source_table, [])
        return FakeCursor(
            tuple((field_name, None, None, None, None, None, None) for field_name in field_names),
            [tuple(row[field_name] for field_name in field_names) for row in rows],
        )

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def activate_member(organization, user, role_name):
    """Aktiv üzvlük (PG ``registrar_guard_active_member`` tələbi)."""

    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={"display_name": role_name.title(), "level": 50, "permissions": []},
    )
    Role.objects.filter(pk=role.pk).update(is_active=True)
    Membership.objects.get_or_create(organization=organization, user=user, role=role, defaults={"is_active": True})
    return role


def factory(rows_by_table):
    connections = []

    def build():
        connection = FakeSourceConnection(rows_by_table)
        connections.append(connection)
        return connection

    build.connections = connections
    return build


# ── mənbə sətir qurucuları ───────────────────────────────────────────────────


def semester_row(legacy_pk=1, name="2021/2022 Payız", type_token="autumn", is_current="0"):
    return {"id": legacy_pk, "name": name, "type": type_token, "is_current": is_current}


def journal_row(legacy_pk, uniqid, **overrides):
    values = {
        "id": legacy_pk,
        "uniqid": uniqid,
        "lesson_id": 64,
        "semestr": 1,
        "groups_id": '["2"]',
        "students_id": f'["{STUDENT_A}","{STUDENT_B}"]',
        "teacher_id": 17,
        "fake": 0,
        "sonra_sil": 0,
        "fenn_saati": 60,
        "active": 1,
        "sillabus_id": SYLLABUS_ID,
    }
    values.update(overrides)
    return values


def sillabus_row(legacy_pk=SYLLABUS_ID, uniqid=SYLLABUS_UNIQID):
    return {"id": legacy_pk, "uniqid": uniqid}


def selfwork_topic_row(legacy_pk, *, uniqid=SYLLABUS_UNIQID, name="Sərbəst iş mövzusu"):
    return {"id": legacy_pk, "uniqid": uniqid, "name": name}


def dates_row(legacy_pk, journal_id=2, month=12, day=30, time_value="14:00"):
    return {"id": legacy_pk, "journal_id": journal_id, "month": month, "day": day, "time": time_value}


def point_row(
    legacy_pk,
    *,
    uniqid=UNIQID,
    month_id="12",
    day_number="30",
    student_id=STUDENT_A,
    point="ie",
    time_value=DEFAULT_TIME,
    excusable=0,
    lab=0,
    sem_muh=0,
    update_counter=0,
    updated_at=None,
    added_date=MAIN_ADDED,
    why="",
    description=None,
    j_id=2,
):
    return {
        "id": legacy_pk,
        "journal_uniqid": uniqid,
        "month_id": month_id,
        "day_number": day_number,
        "student_id": student_id,
        "point": point,
        "added_date": added_date,
        "time": time_value,
        "excusable": excusable,
        "why": why,
        "j_id": j_id,
        "lab": lab,
        "sem_muh": sem_muh,
        "description": description,
        "update_counter": update_counter,
        "updated_at": updated_at,
    }


def allowed_qb_row(legacy_pk, *, student_id=STUDENT_A, start="2021-12-30", end="2021-12-31"):
    return {
        "id": legacy_pk,
        "student_id": student_id,
        "allowed_date_start": datetime.datetime.fromisoformat(f"{start} 08:30:00"),
        "allowed_date_end": datetime.datetime.fromisoformat(f"{end} 23:59:00"),
    }


def yekun_row(
    legacy_pk,
    *,
    student_id=STUDENT_A,
    journal_id=2,
    girish=0.0,
    imtahanda=0.0,
    yekun=0.0,
    **overrides,
):
    values = {
        "id": legacy_pk,
        "student_id": student_id,
        "lesson_id": 64,
        "journal_id": journal_id,
        "girish": girish,
        "imtahanda": imtahanda,
        "yekun": yekun,
        "group_id": 2,
        "kesr": 0,
        "guzest_girish": 0.0,
        "level": 0,
        "guzest_artim": 0.0,
    }
    values.update(overrides)
    return values


def exam_attempt_row(
    legacy_pk,
    *,
    student_id=STUDENT_A,
    lesson_id=64,
    entry=0,
    exit=0,
    attempt_type=0,
    added_date=MAIN_ADDED,
):
    return {
        "id": legacy_pk,
        "student_id": student_id,
        "lesson_id": lesson_id,
        "giris_point": entry,
        "cixis_point": exit,
        "type": attempt_type,
        "added_date": added_date,
    }


def score_sheet_export_row(
    legacy_pk,
    *,
    owner_id=17,
    uniqid=UNIQID,
    data="<table><tr><td>test-only</td></tr></table>",
    export_time=MAIN_ADDED,
):
    return {
        "id": legacy_pk,
        "owner_id": owner_id,
        "uniqid": uniqid,
        "data": data,
        "export_time": export_time,
    }


def tables(
    *,
    semesters=None,
    journals=None,
    dates=None,
    points=None,
    archive=None,
    allowed=None,
    yekun=None,
    syllabi=None,
    topics=None,
    exam_attempts=None,
    score_sheet_exports=None,
):
    """Doqquz cədvəlin tam dəsti — verilməyən hər biri məntiqli defolt alır.

    ``sillabus`` defolt olaraq bir sətirdir (jurnalın ``sillabus_id``-i ona
    düşür), ``sillabus_serbest_is`` isə BOŞdur: mövzuları yalnız J9 testləri
    verir, qalan fazalar onlardan asılı deyil."""

    return {
        SEMESTR_JURNAL_FIELDS.source_table: list(semesters if semesters is not None else [semester_row()]),
        JOURNAL_FIELDS.source_table: list(journals if journals is not None else [journal_row(2, UNIQID)]),
        JOURNAL_DATES_FIELDS.source_table: list(
            dates if dates is not None else [dates_row(10, month=12, day=30), dates_row(11, month=12, day=31)]
        ),
        JOURNAL_POINT_FIELDS.source_table: list(points or []),
        JOURNAL_POINT_ARCHIVE_FIELDS.source_table: list(archive or []),
        ALLOWED_QB_FIELDS.source_table: list(allowed or []),
        YEKUN_FIELDS.source_table: list(yekun or []),
        SILLABUS_FIELDS.source_table: list(syllabi if syllabi is not None else [sillabus_row()]),
        SILLABUS_SELF_WORK_FIELDS.source_table: list(topics or []),
        EXAM_ENTRY_EXIT_FIELDS.source_table: list(exam_attempts or []),
        SCORE_SHEET_EXPORT_FIELDS.source_table: list(score_sheet_exports or []),
    }


def plan(rows_by_table):
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


def allow(**_kwargs):
    return True


def context(*, rows_by_table, run=None, organization=None, actor=None, notes=None, cancelled=None, phase_keys=None):
    return RehearsalContext(
        run_id=run.pk if run is not None else None,
        organization=organization,
        actor=actor,
        authorize=allow,
        target_validators=build_target_validators(),
        policy=policy(phase_keys=phase_keys) if phase_keys else policy(),
        plan=plan(rows_by_table),
        source_connection_factory=factory(rows_by_table),
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=cancelled if cancelled is not None else (lambda: False),
        stdout_note=(notes if notes is not None else []).append,
    )


# ── hədəf/ledger seed ────────────────────────────────────────────────────────


def organization(actor, slug):
    return Organization.objects.create(
        name=f"Journal {slug}",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )


def running_run(org, actor, *, table_plan):
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
    return start_run(run_id=run.pk, actor=actor, authorize=allow)


def _seed_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _map(run_id, actor, *, entity_type, legacy_pk, label, target_pk):
    upsert_entity_map(
        run_id=run_id,
        actor=actor,
        authorize=allow,
        entity_type=entity_type,
        legacy_pk=legacy_pk,
        source_row_hash=_seed_hash(f"{entity_type}:{legacy_pk}"),
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label=label,
        target_pk=str(target_pk),
        target_validators=build_target_validators(),
    )


def seed_journal_target(
    org,
    actor,
    run_id,
    *,
    uniqid=UNIQID,
    students=(STUDENT_A, STUDENT_B),
    lesson_slots=DEFAULT_LESSON_SLOTS,
    period_end=DEFAULT_PERIOD_END,
    code="MYEDU-64",
    offering=None,
    group_ref="2",
):
    """J1/J2/J3-ün qoyub getdiyi hədəflər + ledger xəritələri.

    2026-08-28 (qrup-başına jurnal): J1/J3 möhür açarları artıq DİLİM
    açarlarıdır (``uniqid:<qrup>`` və ``<dates_pk>:<qrup>``) — ``group_ref``
    ``journal_row``-un ``groups_id`` defoltu (``["2"]``) ilə eyni olmalıdır.
    """

    if offering is None:
        subject = django_apps.get_model("registrar", "Subject").objects.create(
            organization=org, code=code, name=f"Fənn {code}", ects=5
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name=f"Payız {code}",
            academic_year="2021/2022",
            period_type=AcademicPeriodType.SEMESTER,
            start_date=datetime.date(2021, 9, 15),
            end_date=period_end,
        )
        offering = django_apps.get_model("registrar", "CourseOffering").objects.create(
            organization=org, subject=subject, period=period, lesson_hours=0, is_active=True
        )
        django_apps.get_model("registrar", "AssessmentScheme").objects.get_or_create(
            organization=org, offering=offering
        )
    _map(
        run_id,
        actor,
        entity_type=COURSE_OFFERING_ENTITY_TYPE,
        legacy_pk=f"{uniqid}:{group_ref}",
        label=COURSE_OFFERING_MODEL_LABEL,
        target_pk=offering.pk,
    )

    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    user_model = get_user_model()
    enrollments = {}
    for legacy_student in students:
        student, _created = user_model.objects.get_or_create(
            username=f"myedu.student.{legacy_student}", defaults={"email": ""}
        )
        profile = student.profile
        profile.organization = org
        profile.save(update_fields=["organization"])
        # PG ``registrar_guard_active_member``: Enrollment.student AKTİV üzvlük
        # tələb edir. Real axında bunu ``sar_materialisation`` (order 28) bu
        # fazalardan (40-48) ƏVVƏL verir — fixture həmin vəziyyəti qurur.
        activate_member(org, student, "student")
        enrollment = enrollment_model.objects.create(
            organization=org, student=student, offering=offering, kind="mandatory"
        )
        enrollments[legacy_student] = enrollment
        _map(
            run_id,
            actor,
            entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
            legacy_pk=f"{uniqid}:{legacy_student}",
            label=ENROLLMENT_MODEL_LABEL,
            target_pk=enrollment.pk,
        )

    lesson_model = django_apps.get_model("registrar", "Lesson")
    lessons = {}
    for dates_pk, date, start_time in lesson_slots:
        lesson = lesson_model.objects.create(
            organization=org, offering=offering, date=date, start_time=start_time, kind="lecture", hours=2
        )
        lessons[dates_pk] = lesson
        _map(
            run_id,
            actor,
            entity_type=LESSON_ENTITY_TYPE,
            legacy_pk=f"{dates_pk}:{group_ref}",
            label=LESSON_MODEL_LABEL,
            target_pk=lesson.pk,
        )
    return offering, enrollments, lessons
