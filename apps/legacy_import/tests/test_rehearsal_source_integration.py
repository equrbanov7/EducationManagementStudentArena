"""Real-source rehearsal conformance (SPEC §15.3/56 and FAZA 3 §8/11).

Written but NEVER run by the implementer (coordination note N5 / FAZA 3 V-5).
It opts in only when the caller provides BOTH a guarded disposable MariaDB
endpoint and a PostgreSQL target, and it drops everything it created in
``finally``.

Two things are deliberately stubbed even here: the 2.14 GB snapshot preflight
(the file is not part of the repository) and the disposable-target interlock
(the CI PostgreSQL database carries no ``ALTER DATABASE … SET
emsarena.rehearsal_target`` marker).  The real interlock is proven separately by
``test_rehearsal_postgres.test_target_guard_reads_real_disposable_marker``.

The second test drives EIGHTEEN of the registry's NINETEEN phases —
``journal_selfwork`` (J9, order 45) is DELIBERATELY not selected because the
synthetic fixture carries no syllabus shapes (``journals.sillabus_id`` column,
``sillabus`` and ``sillabus_serbest_is`` tables); ``select_phases`` accepts a
subset, so an eighteen-key policy is legitimate, not stale.  The phases run are
``academic_structure``
(31 + 83 + 766 rows), ``academic_catalog`` (2 521 + 126 + 3 424),
``identity_cohort`` (7 816 + 729), the three derived identity phases, and the
FAZA 3B journal cluster (J0-J8) and the immutable-evidence tail, fed by nine
synthetic journal tables
(``semestr_jurnal`` 13, ``journals`` 30, ``journals_dates_added_by_teacher`` 60,
``journals_dates_points`` 200, its archive 20, ``allowed_qb`` 5, ``yekun`` 10,
``imthngrscxsblr`` 3, ``balvereqi_logs`` 2).
Every batch-backed table keeps its canonical shape, so ``totals.source_rows`` is
still the real 15 496 — the derived journal phases declare 0 source rows by
contract.

J4-J6 deliberately materialise NOTHING here: ``registrar_guard_active_member``
refuses an ``Enrollment`` whose student is a staged (inactive) account, so the
fixture carries only unresolved student references and every grade cell lands on
the ``*_enrollment_unresolved`` rung.  That is exactly the J2 note above; the
materialise paths are proven in the sqlite unit suite
(``test_rehearsal_journal_marks_phase`` and friends).  What this conformance run
proves for J4-J8 is the SOURCE side: the two-pass duplicate election, the
archive cutoff, the classification ladder, the lock decision and the
reconciliation balance — all of it byte-for-byte deterministic.
"""

import json
import os
import re
from dataclasses import replace
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction

import pymysql
import pytest

from apps.accounts.identity_models import AccountActivationEvidence
from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services import rehearsal_phase_a as phase_a_module
from apps.legacy_import.services.field_contracts import (
    ALLOWED_QB_FIELDS,
    CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS,
    DEPARTMENT_STRUCTURE_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    LESSON_CATALOG_FIELDS,
    SEMESTR_JURNAL_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
    STUDENT_IDENTITY_FIELDS,
    STUDENT_STATUS_FIELDS,
    WORKER_IDENTITY_FIELDS,
    YEKUN_FIELDS,
)
from apps.legacy_import.services.legacy_grade_field_contracts import (
    EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS,
    YEKUN_EVIDENCE_FIELDS,
)
from apps.legacy_import.services.mariadb_gateway import MariaDBSourceConfig, build_configured_mariadb_source_factory
from apps.legacy_import.services.rehearsal_contracts import (
    EmailTrustPolicy,
    LegacyRehearsalInterrupted,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from apps.legacy_import.services.rehearsal_identity_phase import email_evidence_digest
from apps.legacy_import.services.rehearsal_orchestrator import execute_rehearsal
from apps.legacy_import.services.rehearsal_target_guard import TargetGuardAttestation
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256, LegacyTablePlan, load_legacy_table_plan
from apps.legacy_import.tests.test_rehearsal_identity_phase import _plan
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import set_rls_tenant

pytestmark = [pytest.mark.mariadb, pytest.mark.postgres, pytest.mark.django_db]

_HOST = "127.0.0.1"
_ROOT_PASSWORD = "local-conformance-root-only"
_READER_USER = "legacy_rehearsal_reader"
_READER_PASSWORD = "local-conformance-rehearsal-reader-only"
_DATABASE_PATTERN = re.compile(r"emsarena_rehearsal_src_[a-f0-9]{12}\Z")
_CREDENTIAL_VALUE = "credential-never-leaves-the-source"
_PRIVATE_VALUE = "private-never-reported"
_SOURCE_PATH = "/nonexistent/legacy-snapshot.sql"
_SOURCE_SIZE_BYTES = 2_142_912_818
_STUDENT_EMAILS = ("rehearsal-student-1@example.test", "rehearsal-student-2@example.test")
_WORKER_EMAILS = ("rehearsal-worker-1@example.test",)

_GUARD = TargetGuardAttestation(
    vendor="postgresql",
    database_name_shape="emsarena_rehearsal_<12hex>",
    loopback=True,
    non_default_port=True,
    disposable_marker=True,
    role_is_superuser=False,
    role_bypasses_rls=False,
    rls_bypass_active=False,
    migration_head_digest="e" * 64,
)


def _guarded_endpoint():
    if os.getenv("LEGACY_REHEARSAL_SOURCE_DISPOSABLE_GUARD") != "local-container-only":
        pytest.skip("disposable rehearsal MariaDB guard is not enabled")
    if connection.vendor != "postgresql":
        pytest.skip("the rehearsal target must be PostgreSQL")
    database = os.getenv("LEGACY_REHEARSAL_SOURCE_DISPOSABLE_DATABASE", "")
    if not _DATABASE_PATTERN.fullmatch(database):
        pytest.fail("disposable rehearsal source database name is not safely scoped")
    try:
        port = int(os.getenv("LEGACY_REHEARSAL_SOURCE_DISPOSABLE_PORT", ""))
    except ValueError:
        pytest.fail("disposable rehearsal source port is invalid")
    if port == 3306 or not 1024 <= port <= 65535:
        pytest.fail("disposable rehearsal source must use a non-default loopback port")
    return port, database


def _root_connection(port, database=None):
    kwargs = {
        "host": _HOST,
        "port": port,
        "user": "root",
        "password": _ROOT_PASSWORD,
        "charset": "utf8mb4",
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
        "autocommit": True,
        "ssl_disabled": True,
    }
    if database is not None:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


def _create_table(cursor, *, database, table, contract, decoys, emails):
    columns = [f"`{field_name}` VARCHAR(191) NULL" for field_name in contract.allowed_fields if field_name != "id"]
    columns.insert(0, "`id` BIGINT NOT NULL AUTO_INCREMENT")
    columns.extend(f"`{decoy}` VARCHAR(191) NULL" for decoy in decoys)
    columns.append("PRIMARY KEY (`id`)")
    cursor.execute(f"CREATE TABLE `{database}`.`{table}` ({', '.join(columns)}) ENGINE=InnoDB")

    insert_fields = (*contract.allowed_fields, *decoys)
    statement = (
        f"INSERT INTO `{database}`.`{table}` "
        f"({', '.join(f'`{field}`' for field in insert_fields)}) "
        f"VALUES ({', '.join(['%s'] * len(insert_fields))})"
    )
    for index, email in enumerate(emails, start=1):
        values = [f"{_PRIVATE_VALUE}-{table}-{index}-{position}" for position in range(len(insert_fields))]
        values[0] = str(index)
        values[contract.allowed_fields.index("email")] = email
        values[-len(decoys) :] = [_CREDENTIAL_VALUE] * len(decoys)
        cursor.execute(statement, values)


def _create_source_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(f"CREATE USER IF NOT EXISTS '{_READER_USER}'@'%' IDENTIFIED BY '{_READER_PASSWORD}'")
            _create_table(
                cursor,
                database=database,
                table="students",
                contract=STUDENT_IDENTITY_FIELDS,
                decoys=("password", "show_password"),
                emails=_STUDENT_EMAILS,
            )
            _create_table(
                cursor,
                database=database,
                table="workers",
                contract=WORKER_IDENTITY_FIELDS,
                decoys=("password", "pin_for_lock"),
                emails=_WORKER_EMAILS,
            )
            cursor.execute(f"GRANT SELECT ON `{database}`.* TO '{_READER_USER}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            cursor.execute("SET GLOBAL read_only = ON")
    finally:
        root.close()


def _drop_source_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.execute(f"DROP USER IF EXISTS '{_READER_USER}'@'%'")
    finally:
        root.close()


def _source_factory_builder(port, database, opened):
    def build(_settings_object):
        config = MariaDBSourceConfig(
            host=_HOST,
            port=port,
            user=_READER_USER,
            password=_READER_PASSWORD,
            database=database,
            ca_path=None,
            deployment_mode="test",
            local_disposable=True,
            connect_timeout=5,
            read_timeout=30,
            write_timeout=10,
            charset="utf8mb4",
        )
        factory = build_configured_mariadb_source_factory(config)

        def tracked():
            source = factory()
            opened.append(source)
            return source

        return tracked

    return build


def _preflight(**_kwargs):
    return SimpleNamespace(digest=SOURCE_SNAPSHOT_SHA256, size=_SOURCE_SIZE_BYTES)


def _policy():
    return RehearsalPolicy(
        phase_keys=("identity_cohort",),
        username_policy=UsernamePolicy.LEGACY_KEY,
        student_identifier_policy=StudentIdentifierPolicy.LEGACY_PK,
        email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST,
        email_trust_manifest_digest="c" * 64,
        batch_rows=1,
        source_chunk_size=2,
        max_staged_accounts=2,
        student_role_name="student",
        worker_role_name="teacher",
    )


def _organization():
    owner = get_user_model().objects.create_superuser(
        username="rehearsal_source_actor",
        email="rehearsal-source-actor@example.test",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Rehearsal Source Organization",
        slug="rehearsal-source-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    return organization, owner


def test_disposable_mariadb_and_postgres_identity_rehearsal_conformance(monkeypatch, tmp_path):
    port, database = _guarded_endpoint()
    _create_source_fixture(port, database)
    opened = []
    try:
        plan = _plan(students=len(_STUDENT_EMAILS), workers=len(_WORKER_EMAILS))
        monkeypatch.setattr(phase_a_module, "load_legacy_table_plan", lambda: plan)
        monkeypatch.setattr(phase_a_module, "assert_disposable_rehearsal_target", lambda **_kwargs: _GUARD)
        organization, actor = _organization()
        manifest = frozenset({email_evidence_digest(_STUDENT_EMAILS[0]), email_evidence_digest(_WORKER_EMAILS[0])})
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        arguments = {
            "settings_object": SimpleNamespace(),
            "policy": _policy(),
            "organization": organization,
            "actor": actor,
            "report_dir": str(report_dir),
            "apply_confirmation": connection.settings_dict["NAME"],
            "source_path": _SOURCE_PATH,
            "source_size_bytes": _SOURCE_SIZE_BYTES,
            "email_trust_manifest_digests": manifest,
            "source_preflight": _preflight,
            "source_factory_builder": _source_factory_builder(port, database, opened),
        }

        # 1) An injected interruption at the first sealed window boundary.
        state = {"cancelled": False}
        with pytest.raises(LegacyRehearsalInterrupted) as exc_info:
            execute_rehearsal(
                rehearsal_ordinal=1,
                cancellation_requested=lambda: state["cancelled"],
                stdout_note=lambda _note: state.update(cancelled=True),
                **arguments,
            )
        assert exc_info.value.code == "legacy_rehearsal_cancelled"
        run = LegacyMigrationRun.objects.get(organization=organization)
        assert run.status == LegacyMigrationRun.Status.RUNNING
        assert LegacyImportBatch.objects.filter(run=run).count() == 1

        # 2) The resumed pass completes the same windows without duplicating one.
        outcome = execute_rehearsal(rehearsal_ordinal=1, resume_run_id=run.pk, **arguments)

        run.refresh_from_db()
        assert outcome.status == LegacyMigrationRun.Status.SUCCEEDED
        assert run.migrated_count == 2
        assert run.skipped_count == 1
        assert run.quarantined_count == 0
        assert run.migrated_count + run.skipped_count + run.quarantined_count == run.source_row_count
        assert LegacyImportBatch.objects.filter(run=run).count() == 3
        assert LegacyImportBatch.objects.filter(run=run).values_list("source_table", "sequence").distinct().count() == 3

        # 3) Exactly two staged accounts, all of them locked out.
        staged = get_user_model()._default_manager.filter(username__startswith="myedu.")
        assert staged.count() == 2
        for user in staged:
            assert user.is_active is False
            assert user.has_usable_password() is False
            assert user.memberships.get(organization=organization).is_active is False

        # 4) Regenerating the report from the ledger reproduces the same digest.
        regenerated = execute_rehearsal(
            rehearsal_ordinal=2,
            resume_run_id=run.pk,
            emit_report_only=True,
            **arguments,
        )
        assert regenerated.determinism_digest == outcome.determinism_digest

        # 5) Zero credential or raw-value leakage anywhere in the artifacts.
        document = open(outcome.report_path, encoding="ascii").read()
        payload = json.dumps(outcome.payload, ensure_ascii=True, sort_keys=True)
        for forbidden in (
            _CREDENTIAL_VALUE,
            _PRIVATE_VALUE,
            _READER_USER,
            _READER_PASSWORD,
            database,
            _HOST,
            _SOURCE_PATH,
            actor.username,
            "password",
            "pin_for_lock",
            *_STUDENT_EMAILS,
            *_WORKER_EMAILS,
            "myedu.student.1",
        ):
            assert forbidden not in document
            assert forbidden not in payload
        assert json.loads(document)["deterministic"]["totals"]["credential_field_output_count"] == 0
        assert json.loads(document)["deterministic"]["totals"]["raw_pii_field_output_count"] == 0

        # 6) Every raw source transport was closed by the audited adapter.
        assert opened
        assert all(getattr(source, "closed", True) for source in opened)
    finally:
        _drop_source_fixture(port, database)


# ---------------------------------------------------------------------------
# FAZA 3 — SLICE 1 + SLICE 2 + FAZA 3B J0-J3 (SPEC §8/11, §10 items 14-15 and
# FAZA3B qapı 3): the full TEN phase registry.  The batch-backed tables keep the
# CANONICAL plan shapes so the accounting totals are real; only the two big
# journal tables are narrowed to the synthetic fixture (see
# ``_journal_scaled_plan`` — no phase declares them into ``source_rows``).
# ---------------------------------------------------------------------------

_CANONICAL_PLAN = load_legacy_table_plan()
_DEPARTMENT_ROWS = _CANONICAL_PLAN.entry_for("departments").expected_rows  # 31
_SPECIALITY_ROWS = _CANONICAL_PLAN.entry_for("speciality").expected_rows  # 83
_GROUP_ROWS = _CANONICAL_PLAN.entry_for("groups").expected_rows  # 766
_LESSON_ROWS = _CANONICAL_PLAN.entry_for("lessons").expected_rows  # 2 521
_CURRICULUM_ROWS = _CANONICAL_PLAN.entry_for("curricula").expected_rows  # 126
_PLAN_ROWS = _CANONICAL_PLAN.entry_for("curricula_plan").expected_rows  # 3 424
_FULL_STUDENT_ROWS = _CANONICAL_PLAN.entry_for("students").expected_rows  # 7 816
_FULL_WORKER_ROWS = _CANONICAL_PLAN.entry_for("workers").expected_rows  # 729
_STRUCTURE_SOURCE_ROWS = _DEPARTMENT_ROWS + _SPECIALITY_ROWS + _GROUP_ROWS  # 880
_CATALOG_SOURCE_ROWS = _LESSON_ROWS + _CURRICULUM_ROWS + _PLAN_ROWS  # 6 071
_IDENTITY_SOURCE_ROWS = _FULL_STUDENT_ROWS + _FULL_WORKER_ROWS  # 8 545
_FULL_SOURCE_ROWS = _STRUCTURE_SOURCE_ROWS + _CATALOG_SOURCE_ROWS + _IDENTITY_SOURCE_ROWS
# FAZA 3B J0-J3: jurnal klasterinin sintetik guşələri.  ``semestr_jurnal``
# kanonik 13-dür; ``journals``/``journals_dates_added_by_teacher`` isə YALNIZ
# plan-patch ilə kiçildilir (canlı 13 875 / 379 215 sətri burada axıtmaq
# konformans testini saatlara çevirərdi).  Heç bir faza bu cədvəlləri
# ``declared_source_rows``-a saymır, ona görə ``totals.source_rows`` == 15 496
# və registry barmaq izi kanonik qalır.
_SEMESTR_JURNAL_ROWS = _CANONICAL_PLAN.entry_for("semestr_jurnal").expected_rows  # 13
_JOURNAL_ROWS = 30
_JOURNAL_DATE_ROWS = 60
# FAZA 3B J4-J8: qiymət klasterinin sintetik guşələri.  Canlı ölçülər
# (5 135 289 / 776 033 / 2 964 / 17 194) burada axıdılsaydı konformans testi
# saatlarla işləyərdi; heç bir faza bu cədvəlləri ``declared_source_rows``-a
# saymır, ona görə ``totals.source_rows`` yenə 15 496 qalır.
_JOURNAL_POINT_ROWS = 200
_JOURNAL_ARCHIVE_ROWS = 20
_ALLOWED_QB_ROWS = 5
_YEKUN_ROWS = 10
_EXAM_ATTEMPT_ROWS = 3
_SCORE_SHEET_EXPORT_ROWS = 2
# Bal sətirləri yalnız BU dörd MIGRATED jurnala (və 3 nömrəli V6-süzülmüş
# jurnala) toxunur — jurnal-səviyyə möhür sayları belə dəqiq hesablana bilir.
_POINT_JOURNALS = (1, 2, 6, 7)
_POINT_ORPHAN_JOURNAL = 3
# J1 nəticəsi: bu 21 jurnal MIGRATED offering alır (aşağıdakı ``_journal_values``
# xüsusi halları ilə birgə oxu); J3 defolt dərs sətirləri yalnız bunlara bağlanır.
_JOURNAL_MIGRATED_IDS = (1, 2, 6, 7, *range(14, 31))
# Registry order, not alphabetical: 10 < 12 < 20 < 25 < 26 < 28 < 32 < 34 < 36 < 38.
_FULL_PHASE_KEYS = (
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
    "legacy_grade_facts",
    "journal_reconcile",
    "legacy_grade_artifacts",
)
_FULL_PHASE_ORDERS = [10, 12, 20, 25, 26, 28, 32, 34, 36, 38, 40, 42, 43, 44, 46, 47, 48, 49]


def _journal_scaled_plan():
    """Kanonik plan, YALNIZ iki jurnal cədvəli sintetik ölçüyə endirilmiş.

    Batch-backed cədvəllərin (structure/catalog/identity) girişləri toxunulmaz
    qalır — ``declared_source_rows`` cəmi, ``schema_version`` və registry
    barmaq izi kanonik dəyərlərində qalır; dəyişən yalnız J1/J2/J3 axınlarının
    sətir-sayı qapısıdır (axın ``expected_rows``-a TAM bərabərlik tələb edir).
    """

    scaled = {
        "journals": _JOURNAL_ROWS,
        "journals_dates_added_by_teacher": _JOURNAL_DATE_ROWS,
        "journals_dates_points": _JOURNAL_POINT_ROWS,
        "journals_dates_points_archive": _JOURNAL_ARCHIVE_ROWS,
        "allowed_qb": _ALLOWED_QB_ROWS,
        "yekun": _YEKUN_ROWS,
        "imthngrscxsblr": _EXAM_ATTEMPT_ROWS,
        "balvereqi_logs": _SCORE_SHEET_EXPORT_ROWS,
    }
    entries = tuple(
        replace(entry, expected_rows=scaled[entry.source_table]) if entry.source_table in scaled else entry
        for entry in _CANONICAL_PLAN.entries
    )
    return LegacyTablePlan(
        version=_CANONICAL_PLAN.version,
        fingerprint=_CANONICAL_PLAN.fingerprint,
        source_snapshot_sha256=_CANONICAL_PLAN.source_snapshot_sha256,
        expected_row_count=sum(entry.expected_rows for entry in entries),
        entries=entries,
    )


# Only this many identities are trusted, so exactly this many accounts stage and
# exactly this many placement decisions are derived.  Keeping it small is what
# makes a 9 425-row conformance pass finish in minutes rather than hours.
_TRUSTED_STUDENTS = 40
_TRUSTED_WORKERS = 10

# Columns MariaDB hands back as Python ``int``; the transforms fail closed on a
# string here (A-2), so the disposable fixture must reproduce the real types.
_INT_COLUMNS = {
    "departments": ("department_id", "department_types_id"),
    "speciality": ("department_id",),
    "groups": ("speciality_id", "department_id", "start_year", "curricula_id"),
    "lessons": ("department_id", "only_az"),
    "curricula": ("speciality_id",),
    "curricula_plan": ("curricula_id", "lesson_before_id"),
    # V-18: ``azadedildi`` is read through STUDENT_STATUS_FIELDS with ``_legacy_int``.
    "students": ("group_id", "speciality_id", "azadedildi"),
    # V-22..V-23: ``teacher_type``/``inzibati`` da canlı dump-da ``int``-dir.
    "workers": ("department_id", "teacher_type", "inzibati"),
    # J0-J3: canlı sxemdə (DESCRIBE ilə təsdiqli) bu sütunlar ``int``-dir və
    # ``legacy_int`` mətn görəndə fail-closed olur — fixture real tipi saxlayır.
    "semestr_jurnal": ("is_current",),
    "journals": ("lesson_id", "semestr", "teacher_id", "fake", "sonra_sil", "active", "fenn_saati"),
    "journals_dates_added_by_teacher": ("journal_id", "month", "day"),
    # J4-J8: bal xanalarının rəqəm sütunları (``legacy_flag``/``student_id``
    # mətn görəndə fail-closed olur, ona görə fixture real tipi saxlayır).
    "journals_dates_points": ("student_id", "excusable", "j_id", "lab", "update_counter", "sem_muh"),
    "journals_dates_points_archive": ("student_id", "excusable", "j_id", "lab", "update_counter", "sem_muh"),
    "allowed_qb": ("student_id",),
    # Canlı ``yekun`` DESCRIBE sübutu: bu beş metadata sütunu da INT-dir.
    # Fixture onları VARCHAR yaratsa, sərt source parser real sxemdən fərqli
    # sintetik tip drift-i haqlı olaraq rədd edir.
    "yekun": (
        "student_id",
        "lesson_id",
        "journal_id",
        "group_id",
        "kesr",
        "guzest_girish",
        "level",
        "guzest_artim",
    ),
    "imthngrscxsblr": ("student_id", "lesson_id", "giris_point", "cixis_point", "type"),
    "balvereqi_logs": ("owner_id",),
}
# ``added_date``/``updated_at``/``allowed_date_*`` DATETIME, ``time`` isə TIME
# olmalıdır: J-V7 kəsimi, J-V4 sıralaması və dərs slotu məhz bu tiplərə baxır.
_DATETIME_COLUMNS = {
    "journals_dates_points": ("added_date", "updated_at"),
    "journals_dates_points_archive": ("added_date", "updated_at"),
    "allowed_qb": ("allowed_date_start", "allowed_date_end"),
    "imthngrscxsblr": ("added_date",),
    "balvereqi_logs": ("export_time",),
}
_TIME_COLUMNS = {
    "journals_dates_points": ("time",),
    "journals_dates_points_archive": ("time",),
}
# C-2: ``kredit`` and every ``saat_*`` must arrive as a Python ``float`` — the
# catalogue transform raises ``legacy_rehearsal_source_value_type_unsupported``
# for an ``int`` or a ``Decimal``, so the disposable fixture uses DOUBLE columns.
_FLOAT_COLUMNS = {
    "curricula_plan": ("kredit", "saat_aks", "saat_as", "saat_muh", "saat_sem", "saat_lab", "saat_prak"),
    # J8 çarpaz-yoxlaması: canlı ``yekun`` sütunları FLOAT-dur.
    "yekun": ("girish", "imtahanda", "yekun"),
}


class _MergedSourceContract:
    """The union of the two ``students`` contracts the five-phase run opens.

    ``id`` appears in BOTH ``STUDENT_IDENTITY_FIELDS`` and
    ``STUDENT_STATUS_FIELDS``; a column created twice would make
    ``compile_safe_projection`` refuse the table with
    ``legacy_source_schema_contract_mismatch``, so the union is de-duplicated
    while keeping first-seen order.
    """

    def __init__(self, *contracts):
        fields = [field_name for contract in contracts for field_name in contract.allowed_fields]
        self.allowed_fields = tuple(dict.fromkeys(fields))


_STUDENT_SOURCE_COLUMNS = _MergedSourceContract(STUDENT_IDENTITY_FIELDS, STUDENT_STATUS_FIELDS)


def _full_email(table, index):
    return f"rehearsal-{table}-{index}@example.test"


def _typed_columns(table, contract, decoys):
    integers = _INT_COLUMNS.get(table, ())
    floats = _FLOAT_COLUMNS.get(table, ())
    datetimes = _DATETIME_COLUMNS.get(table, ())
    times = _TIME_COLUMNS.get(table, ())
    columns = ["`id` BIGINT NOT NULL AUTO_INCREMENT"]
    for field_name in contract.allowed_fields:
        if field_name == "id":
            continue
        if field_name in integers:
            sql_type = "BIGINT NULL"
        elif field_name in floats:
            sql_type = "DOUBLE NULL"
        elif field_name in datetimes:
            sql_type = "DATETIME NULL"
        elif field_name in times:
            sql_type = "TIME NULL"
        elif table == "balvereqi_logs" and field_name == "data":
            sql_type = "LONGTEXT NULL"
        else:
            sql_type = "VARCHAR(191) NULL"
        columns.append(f"`{field_name}` {sql_type}")
    columns.extend(f"`{decoy}` VARCHAR(191) NULL" for decoy in decoys)
    columns.append("PRIMARY KEY (`id`)")
    return columns


def _insert_statement(database, table, fields):
    return (
        f"INSERT INTO `{database}`.`{table}` "
        f"({', '.join(f'`{field}`' for field in fields)}) "
        f"VALUES ({', '.join(['%s'] * len(fields))})"
    )


def _seed_table(cursor, *, database, table, contract, decoys, rows, values_for):
    """Create one typed table and bulk-insert ``rows`` generated tuples."""

    cursor.execute(
        f"CREATE TABLE `{database}`.`{table}` ({', '.join(_typed_columns(table, contract, decoys))}) ENGINE=InnoDB"
    )
    fields = (*contract.allowed_fields, *decoys)
    statement = _insert_statement(database, table, fields)
    batch = []
    for legacy_pk in range(1, rows + 1):
        overrides = values_for(legacy_pk)
        values = []
        for position, field_name in enumerate(fields):
            if field_name == "id":
                values.append(legacy_pk)  # AUTO_INCREMENT-ə güvənmə: id == legacy_pk zəmanəti
            elif field_name in overrides:
                values.append(overrides[field_name])
            elif field_name in decoys:
                values.append(_CREDENTIAL_VALUE)
            elif field_name in _INT_COLUMNS.get(table, ()):
                values.append(0)
            elif field_name in _FLOAT_COLUMNS.get(table, ()):
                values.append(0.0)
            elif field_name in _DATETIME_COLUMNS.get(table, ()):
                values.append(None)
            elif field_name in _TIME_COLUMNS.get(table, ()):
                values.append("00:00:00")
            else:
                values.append(f"{_PRIVATE_VALUE}-{table}-{legacy_pk}-{position}")
        batch.append(tuple(values))
        if len(batch) == 500:
            cursor.executemany(statement, batch)
            batch = []
    if batch:
        cursor.executemany(statement, batch)


def _department_values(legacy_pk):
    # 9 faculties, 18 chairs and 4 untyped roots — the live 31-row shape (§9).
    if legacy_pk <= 9:
        type_id, parent = 3, 0
    elif legacy_pk <= 27:
        type_id, parent = 4, ((legacy_pk - 10) % 9) + 1
    else:
        type_id, parent = 0, 0
    return {
        "name": "Kollec" if type_id == 0 else f"Bölmə {legacy_pk}",
        "department_id": parent,
        "department_types_id": type_id,
        "kollec_or_uni": "k" if type_id == 0 else "uni",
    }


def _speciality_values(legacy_pk):
    return {
        # The trailing tab is the live pollution ``clean_code`` has to remove.
        "speciality_code": f"{50000 + legacy_pk:06d}\t" if legacy_pk % 3 else "5555",
        "name": f"İxtisas {legacy_pk}",
        "department_id": ((legacy_pk - 1) % 27) + 1,
    }


def _group_values(legacy_pk):
    speciality = ((legacy_pk - 1) % _SPECIALITY_ROWS) + 1
    return {
        "name": f"Qrup {legacy_pk}",
        "speciality_id": speciality,
        "department_id": ((speciality - 1) % 27) + 1,
        "sector": ("az", "en", "ru")[legacy_pk % 3],
        "eyani_qiyabi": "Əyani" if legacy_pk % 2 else "Qiyabi",
        "bak_or_mag": "mag" if legacy_pk % 5 == 0 else "bak",
        # A third of the live groups carry the NOT-NULL zero-date sentinel (A-8).
        "start_year": 0 if legacy_pk % 3 == 0 else 2015 + (legacy_pk % 8),
        "curricula_id": legacy_pk % 126,
    }


def _student_values(legacy_pk):
    trusted = legacy_pk <= _TRUSTED_STUDENTS
    return {
        "email": _full_email("students", legacy_pk) if trusted else f"student-{legacy_pk}@untrusted.test",
        "group_id": ((legacy_pk - 1) % _GROUP_ROWS) + 1,
        "speciality_id": 0,  # every live row is 0 (§4.5)
        "entry_year": "" if legacy_pk % 4 == 0 else str(2015 + (legacy_pk % 8)),
        "fincode": f"{legacy_pk:07d}" if trusted else "",
        "first_name": f"Ad{legacy_pk}",
        "last_name": f"Soyad{legacy_pk}",
        # V-18(d): the live dump releases ~200 of 7 816 students.  Row 1 is
        # deliberately BOTH trusted and released, so the departed rung is
        # exercised on an account this run actually staged.
        "azadedildi": 1 if legacy_pk == 1 or legacy_pk % 500 == 0 else 0,
    }


def _lesson_values(legacy_pk):
    # V-6: ``lesson_code`` is a category label, not an identity — 145 distinct
    # codes over 2 521 rows.  E-4: a repeated (name, department) pair dedups.
    return {
        "name": f"Fənn {((legacy_pk - 1) % 900) + 1}" if legacy_pk % 250 else "",
        "lesson_code": "37" if legacy_pk % 2 else "01",
        "type": str(legacy_pk % 4),
        "department_id": ((legacy_pk - 1) % 27) + 1,
        "only_az": legacy_pk % 2,
    }


def _curriculum_values(legacy_pk):
    # V-7: ``from_date`` is empty for every live row, so the admission year is
    # derived from the referencing groups; ``to_date`` is decision-token only.
    return {
        "speciality_id": ((legacy_pk - 1) % _SPECIALITY_ROWS) + 1,
        "from_date": "",
        "to_date": "2026" if legacy_pk % 2 else "",
        "eyani_qiyabi": "Əyani" if legacy_pk % 3 else "Qiyabi",
        "bak_or_mag": "mag" if legacy_pk % 7 == 0 else "bak",
    }


def _plan_row_values(legacy_pk):
    lesson = ((legacy_pk - 1) % _LESSON_ROWS) + 1
    # V-8/V-14: 26% of the live rows carry a MULTI-element JSON array, and each
    # element is expanded into its own CurriculumSubject.
    if legacy_pk % 97 == 0:
        lesson_id = f'["{lesson}","{(lesson % _LESSON_ROWS) + 1}"]'
    elif legacy_pk % 331 == 0:
        lesson_id = ""  # the live blank ⇒ quarantined reference
    else:
        lesson_id = f'["{lesson}"]'
    semester = ((legacy_pk - 1) % 7) + 1
    return {
        "curricula_id": ((legacy_pk - 1) % _CURRICULUM_ROWS) + 1,
        "lesson_id": lesson_id,
        "lesson_code": "37",
        # V-9/V-21: the token is evidence only in this slice.
        "type": ("3", "1", "2.1", "4.01", "")[legacy_pk % 5],
        # V-10/V-13: ``payiz_N``/``yaz_N``; under ORDINAL an even ``payiz`` and an
        # odd ``yaz`` contradict the scheme and raise the parity warning.
        "semestr": f"payiz_{semester}" if legacy_pk % 2 else f"yaz_{semester}",
        # V-16/§4: 0.0 contributes nothing and is NOT "unsupported"; 2.5 is never
        # rounded; 6.0 is the only shape that can set an ECTS.
        "kredit": (6.0, 4.0, 0.0, 2.5, 3.0)[legacy_pk % 5],
        "lesson_before_id": lesson if legacy_pk % 11 == 0 else 0,
        "saat_aks": 0.0,
        "saat_as": 0.0,
        "saat_muh": 30.0 if legacy_pk % 3 else 0.0,
        "saat_sem": 0.0,
        "saat_lab": 15.0 if legacy_pk % 5 == 0 else 0.0,
        "saat_prak": 0.0,
    }


def _worker_values(legacy_pk):
    trusted = legacy_pk <= _TRUSTED_WORKERS
    return {
        "email": _full_email("workers", legacy_pk) if trusted else f"worker-{legacy_pk}@untrusted.test",
        "department_id": ((legacy_pk - 1) % 27) + 1,
        "first_name": f"İşçi{legacy_pk}",
        "last_name": f"Soyad{legacy_pk}",
        # V-23: rol qərarına çevrilməyən mənbə faktları — 1..3 həmişə tanınır,
        # ``inzibati == 1`` yalnız INFO bayrağı doğurur.
        "teacher_type": ((legacy_pk - 1) % 3) + 1,
        "inzibati": 1 if legacy_pk % 5 == 0 else 0,
    }


_SEASON_TOKENS = ("autumn", "spring", "summer")
_SEASON_LABELS = {"autumn": "Payız", "spring": "Yaz", "summer": "Yay"}


def _semestr_jurnal_values(legacy_pk):
    # J-V9(F): 11 normal fəsil (2021..2024) + 1 parse-alınmaz sətir (12) +
    # ``is_current=1`` bayraqlı 13-cü sətir.  12 fərqli (il, fəsil) cütü →
    # J0 12 dövr yaradır, 12-ci sətir QUARANTINED ``legacy_journal_period_invalid``.
    if legacy_pk == 12:
        return {"name": "Qış semestri (ilsiz)", "type": "winter", "is_current": 0}
    if legacy_pk == 13:
        return {"name": "2025/2026 Payız", "type": "autumn", "is_current": 1}
    year = 2021 + (legacy_pk - 1) // 3
    season = _SEASON_TOKENS[(legacy_pk - 1) % 3]
    return {"name": f"{year}/{year + 1} {_SEASON_LABELS[season]}", "type": season, "is_current": 0}


def _journal_values(legacy_pk):
    # PG qeydi (registrar_guard_active_member): rehearsal hesabları QEYRİ-AKTİV
    # üzvlüklə stage edir, ona görə MIGRATED offering-ə çevrilən jurnallar
    # QƏSDƏN yalnız həll olunmayan teacher_id (>100, untrusted) daşıyır (V5 →
    # instructor=NULL) və yalnız naməlum tələbə istinadları daşıyır — trusted
    # tələbələr (1..4) yalnız V6-süzülmüş/karantin jurnallardadır (J2 orphan
    # yolu, DB yazısı yoxdur).  Materialise yolları sqlite unit dəstində sübutludur.
    values = {
        "uniqid": f"jrn{legacy_pk:07d}",
        "lesson_id": ((legacy_pk - 1) % 20) + 1,
        "semestr": ((legacy_pk - 1) % 11) + 1,
        "groups_id": f'["{legacy_pk}"]',
        "students_id": f'["{200 + legacy_pk}","{300 + legacy_pk}"]',
        "teacher_id": 100 + legacy_pk,
        "fake": 0,
        "sonra_sil": 0,
        "fenn_saati": 60,
        "active": 1,
    }
    overrides = {
        # J-V6 süzgəci: uniqid ledger-də qalır, target yazısı yoxdur.
        3: {"fake": 1, "students_id": '["1","2"]'},
        4: {"sonra_sil": 1, "students_id": '["3"]'},
        # V6 + J2: boş students_id → jurnal-səviyyə ``legacy_journal_students_invalid``.
        5: {"fake": 1, "sonra_sil": 1, "students_id": "[]"},
        # J-V7 çoxqruplu cüt: eyni (fənn, dövr, group=NULL) açarı → 7-ci jurnal
        # ``legacy_journal_offering_merged`` İNFO-su ilə 6-cının offering-inə qatlanır.
        6: {"lesson_id": 3, "semestr": 2, "groups_id": '["3","4"]'},
        7: {"lesson_id": 3, "semestr": 2, "groups_id": '["5","6"]'},
        # J-V7 karantinləri: parse xətası / boş massiv / tapılmayan qrup.
        8: {"groups_id": "not-json", "students_id": '["4"]'},
        9: {"groups_id": "[]"},
        10: {"groups_id": '["9999"]'},
        # İstinad karantinləri: fənn (lesson 0), dövr (12 J0-da karantindədir),
        # 13-cü sətirdə hər ikisi birgə.
        11: {"lesson_id": 0},
        12: {"semestr": 12},
        13: {"lesson_id": 0, "semestr": 0},
    }
    values.update(overrides.get(legacy_pk, {}))
    return values


def _journal_date_values(legacy_pk):
    # 1..48: MIGRATED jurnallar üzərində 3 dalğa (ay 9-11, saat 08-10) — hər
    # slot jurnal daxilində unikaldır; 6/7 merge cütünün slotları da gün ilə
    # fərqlənir, yəni 48 sətir 48 fərqli ``Lesson`` sətrinə düşür.
    if legacy_pk <= 48:
        wave = (legacy_pk - 1) // 21
        return {
            "journal_id": _JOURNAL_MIGRATED_IDS[(legacy_pk - 1) % 21],
            "month": 9 + wave,
            "day": ((legacy_pk - 1) % 27) + 1,
            "time": f"{8 + wave:02d}:00",
        }
    overrides = {
        # V4 analoqu: 1-ci və 2-ci sətirlərin slot dublikatları — ilk id udur.
        49: {"journal_id": 1, "month": 9, "day": 1, "time": "08:00"},
        50: {"journal_id": 2, "month": 9, "day": 2, "time": "08:00"},
        # Orphan-lar: naməlum id, fake (3), dövr-karantinli (12), sonra_sil (4),
        # qrup-karantinli (8) jurnal — hamısı SKIPPED ``legacy_journal_lesson_orphan``.
        51: {"journal_id": 999, "month": 9, "day": 3, "time": "08:00"},
        52: {"journal_id": 3, "month": 9, "day": 4, "time": "08:00"},
        53: {"journal_id": 12, "month": 9, "day": 5, "time": "08:00"},
        59: {"journal_id": 4, "month": 9, "day": 6, "time": "08:00"},
        60: {"journal_id": 8, "month": 9, "day": 7, "time": "08:00"},
        # Yararsızlar (canlı anomaliyaların güzgüsü): fevral 30, pozuq saat
        # formaları ("83:0_", "1_:__"), ay 0 və ay 13 → QUARANTINED.
        54: {"journal_id": 1, "month": 2, "day": 30, "time": "10:00"},
        55: {"journal_id": 1, "month": 10, "day": 6, "time": "83:0_"},
        56: {"journal_id": 2, "month": 10, "day": 7, "time": "1_:__"},
        57: {"journal_id": 6, "month": 0, "day": 5, "time": "09:00"},
        58: {"journal_id": 7, "month": 13, "day": 5, "time": "09:00"},
    }
    return overrides[legacy_pk]


# ── FAZA 3B J4-J8: bal xanaları, arxiv, üzürlü qaib və ``yekun`` ────────────
#
# Sətir sayları QƏSDƏN dəqiq bölünür ki, jurnal-səviyyə möhür sayları əl ilə
# yoxlana bilsin (aşağıdakı ``journal_states`` assert-i):
#   marks   80 = 20 dublikat uduzanı + 2 boş + 3 diapazon + 3 naməlum
#              + 32 qeydiyyat-həllsiz + 10 pozuq gün + 10 orphan
#   comps   50 = 8 boş + 8 naməlum + 8 diapazon + 16 qeydiyyat-həllsiz + 10 orphan
#   finals  70 = 2 boş + 35 naməlum kod + 1 diapazon + 22 qeydiyyat-həllsiz + 10 orphan
_POINT_BEFORE_CUTOFF = "2022-01-05 09:00:00"  # J-V7 kəsimindən ƏVVƏL
_POINT_AFTER_CUTOFF = "2022-06-05 09:00:00"  # kəsimdən SONRA → overlap
_POINT_MAIN_ADDED = "2022-04-01 09:00:00"
_MARK_POINT_CYCLE = ("ie", "qb", "8", "", "89", "wr", "0", "10")
_COMPONENT_MONTHS = ("k1", "k2", "k3", "si")
_COMPONENT_POINT_CYCLE = ("9", "", "qb", "11", "3")
_FINAL_MONTHS = ("im", "im2", "pa", "wr", "ga")
_FINAL_POINT_CYCLE = ("45", "30", "7", "5", "2")
_FINAL_EDGE_ROWS = {
    181: ("im", ""),
    182: ("im", "l"),
    183: ("im", "101"),
    184: ("im2", ""),
    185: ("im", "89"),
    186: ("ss", "3"),
    187: ("ww", "4"),
    188: ("ll", "6"),
    189: ("rr", "2"),
    190: ("im2", "12"),
}


def _point_defaults(legacy_pk, *, journal, month_id, day_number, point, added_date, **overrides):
    values = {
        "journal_uniqid": f"jrn{journal:07d}",
        "month_id": month_id,
        "day_number": day_number,
        "student_id": 1_000 + legacy_pk,
        "point": point,
        "added_date": added_date,
        "time": "08:00:00",
        "excusable": 0,
        "why": "",
        "j_id": journal,
        "lab": 0,
        "description": "",
        "update_counter": 0,
        "updated_at": None,
    }
    values.update(overrides)
    return values


def _journal_point_values(legacy_pk):
    """200 sətir: dəyər nərdivanı, J-V4 dublikatı, pozuq gün, orphan, psevdo-kodlar."""

    if legacy_pk <= 40:  # təqvim xanaları — bütün ``point`` formaları
        offset = legacy_pk - 1
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[offset % 4],
            month_id="09",
            day_number=f"{(offset % 4) + 1:02d}",
            point=_MARK_POINT_CYCLE[offset % 8],
            added_date=_POINT_MAIN_ADDED,
        )
    if legacy_pk <= 60:  # J-V4: 1-20 sətirlərinin xanalarını daha yüksək sayğacla təkrarlayır
        base = legacy_pk - 40
        offset = base - 1
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[offset % 4],
            month_id="09",
            day_number=f"{(offset % 4) + 1:02d}",
            point="6",
            added_date=_POINT_MAIN_ADDED,
            student_id=1_000 + base,
            update_counter=5,
        )
    if legacy_pk <= 70:  # pozuq gün nömrəsi → dərs slotu həll olunmur (səssiz düşmür)
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[(legacy_pk - 61) % 4],
            month_id="09",
            day_number="00",
            point="ie",
            added_date=_POINT_MAIN_ADDED,
        )
    if legacy_pk <= 80:  # V6-süzülmüş jurnalın sətirləri → orphan
        return _point_defaults(
            legacy_pk,
            journal=_POINT_ORPHAN_JOURNAL,
            month_id="09",
            day_number="01",
            point="ie",
            added_date=_POINT_MAIN_ADDED,
        )
    if legacy_pk <= 120:  # k1/k2/k3/si komponent xanaları
        offset = legacy_pk - 81
        month_id = _COMPONENT_MONTHS[offset % 4]
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[(offset // 4) % 4],
            month_id=month_id,
            day_number=month_id,
            point=_COMPONENT_POINT_CYCLE[offset % 5],
            added_date=_POINT_MAIN_ADDED,
            time="00:00:00",
        )
    if legacy_pk <= 130:  # orphan jurnalın komponent xanaları
        return _point_defaults(
            legacy_pk,
            journal=_POINT_ORPHAN_JOURNAL,
            month_id="k1",
            day_number="k1",
            point="8",
            added_date=_POINT_MAIN_ADDED,
            time="00:00:00",
        )
    if legacy_pk <= 180:  # im/im2 + J-V13 naməlum kodları
        offset = legacy_pk - 131
        month_id = _FINAL_MONTHS[offset % 5]
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[(offset // 5) % 4],
            month_id=month_id,
            day_number=month_id,
            point=_FINAL_POINT_CYCLE[offset % 5],
            added_date=_POINT_MAIN_ADDED,
            time="00:00:00",
        )
    if legacy_pk <= 190:  # yekun/təkrar imtahanın kənar halları (hamısı 1-ci jurnalda)
        month_id, point = _FINAL_EDGE_ROWS[legacy_pk]
        return _point_defaults(
            legacy_pk,
            journal=_POINT_JOURNALS[0],
            month_id=month_id,
            day_number=month_id,
            point=point,
            added_date=_POINT_MAIN_ADDED,
            time="00:00:00",
        )
    return _point_defaults(  # orphan jurnalın yekun xanaları
        legacy_pk,
        journal=_POINT_ORPHAN_JOURNAL,
        month_id="im",
        day_number="im",
        point="40",
        added_date=_POINT_MAIN_ADDED,
        time="00:00:00",
    )


def _journal_point_archive_values(legacy_pk):
    """J-V7: ilk 10 sətir kəsimdən ƏVVƏL, son 10 sətir SONRA (overlap)."""

    offset = legacy_pk - 1
    return _point_defaults(
        legacy_pk,
        journal=_POINT_JOURNALS[offset % 4],
        month_id="09",
        day_number="01",
        point="ie",
        added_date=_POINT_BEFORE_CUTOFF if legacy_pk <= 10 else _POINT_AFTER_CUTOFF,
        student_id=2_000 + legacy_pk,
    )


def _allowed_qb_values(legacy_pk):
    # Heç bir sətrin tələbəsi bu run-da həll olunmur — pəncərə axını yoxlanılır.
    return {
        "student_id": 9_000 + legacy_pk,
        "allowed_date_start": "2021-12-30 08:30:00",
        "allowed_date_end": "2021-12-31 23:59:00",
    }


def _yekun_values(legacy_pk):
    # Jurnal həll olunur, qeydiyyat OLUNMUR → J8 sətri "unresolved" möhürləyir.
    return {
        "student_id": 1_000 + legacy_pk,
        "lesson_id": 1,
        "journal_id": _POINT_JOURNALS[(legacy_pk - 1) % 4],
        "girish": 20.0,
        "imtahanda": 30.0,
        "yekun": 50.0,
        # `grade-evidence-v1` proyeksiyasının əlavə sütunları — semantikası
        # TƏSDİQLƏNMƏYİB, ona görə yalnız XAM sübut kimi saxlanılır (heç bir
        # hesablamaya girmir).  Fixture real sxemin tiplərini güzgüləyir.
        "group_id": 7,
        "kesr": legacy_pk % 2,
        "guzest_girish": 0,
        "level": 0,
        "guzest_artim": 0,
    }


def _exam_attempt_values(legacy_pk):
    return {
        "student_id": 9_500 + legacy_pk,
        "lesson_id": legacy_pk,
        "giris_point": 3010 if legacy_pk == 1 else 20 + legacy_pk,
        "cixis_point": 2437 if legacy_pk == 1 else 30 + legacy_pk,
        "type": legacy_pk % 4,
        "added_date": f"2022-04-0{legacy_pk} 09:00:00",
    }


def _score_sheet_export_values(legacy_pk):
    return {
        "owner_id": legacy_pk,
        "uniqid": f"jrn{legacy_pk:07d}",
        "data": f"<table><tr><td>{_PRIVATE_VALUE}-{legacy_pk}</td><td>{40 + legacy_pk}</td></tr></table>",
        "export_time": f"2023-08-{13 + legacy_pk:02d} 10:00:00",
    }


# ``yekun`` cədvəli İKİ kontrakt tərəfindən oxunur: dar ``YEKUN_FIELDS``
# (J5b/J8 möhür resepti) və geniş ``YEKUN_EVIDENCE_FIELDS`` (qiymət sübutu).
# ``compile_safe_projection`` kontraktın sxemin ALT-ÇOXLUĞU olmasını tələb edir,
# ona görə fixture cədvəli GENİŞ proyeksiya ilə qurur.  Bu invariant pozulsa
# (məsələn dar kontrakta geniş kontraktda olmayan sütun əlavə edilsə) sintetik
# dəst `legacy_source_schema_contract_mismatch` ilə çökür — 2026-08-30-da məhz
# belə oldu.  Modul yüklənəndə dərhal tutulsun deyə burada yoxlanılır.
assert set(YEKUN_FIELDS.allowed_fields) <= set(YEKUN_EVIDENCE_FIELDS.allowed_fields), (
    "dar `YEKUN_FIELDS` geniş `YEKUN_EVIDENCE_FIELDS`-in alt-çoxluğu olmalıdır; "
    "əks halda fixture cədvəli hər iki oxucuya xidmət edə bilməz"
)


_FULL_TABLES = (
    ("departments", DEPARTMENT_STRUCTURE_FIELDS, (), _DEPARTMENT_ROWS, _department_values),
    ("speciality", SPECIALITY_STRUCTURE_FIELDS, (), _SPECIALITY_ROWS, _speciality_values),
    ("groups", GROUP_STRUCTURE_FIELDS, (), _GROUP_ROWS, _group_values),
    ("lessons", LESSON_CATALOG_FIELDS, (), _LESSON_ROWS, _lesson_values),
    ("curricula", CURRICULUM_CATALOG_FIELDS, (), _CURRICULUM_ROWS, _curriculum_values),
    ("curricula_plan", CURRICULUM_PLAN_FIELDS, (), _PLAN_ROWS, _plan_row_values),
    # The union of the identity and status contracts: the SAR phase opens TWO
    # ``students`` streams and ``id`` may only be created once (V-18(a)).
    ("students", _STUDENT_SOURCE_COLUMNS, ("password", "show_password"), _FULL_STUDENT_ROWS, _student_values),
    ("workers", WORKER_IDENTITY_FIELDS, ("password", "pin_for_lock"), _FULL_WORKER_ROWS, _worker_values),
    # FAZA 3B J0-J3: jurnal klasteri (``journals`` J1/J2/J3-də, ``semestr_jurnal``
    # J0/J3-də eyni audited kontraktla yenidən axıdılır — cədvəl bir dəfə yaranır).
    ("semestr_jurnal", SEMESTR_JURNAL_FIELDS, (), _SEMESTR_JURNAL_ROWS, _semestr_jurnal_values),
    ("journals", JOURNAL_FIELDS, (), _JOURNAL_ROWS, _journal_values),
    ("journals_dates_added_by_teacher", JOURNAL_DATES_FIELDS, (), _JOURNAL_DATE_ROWS, _journal_date_values),
    # FAZA 3B J4-J8: bal xanaları, arxivi, üzürlü qaib pəncərələri və ``yekun``.
    ("journals_dates_points", JOURNAL_POINT_FIELDS, (), _JOURNAL_POINT_ROWS, _journal_point_values),
    (
        "journals_dates_points_archive",
        JOURNAL_POINT_ARCHIVE_FIELDS,
        (),
        _JOURNAL_ARCHIVE_ROWS,
        _journal_point_archive_values,
    ),
    ("allowed_qb", ALLOWED_QB_FIELDS, (), _ALLOWED_QB_ROWS, _allowed_qb_values),
    # Cədvəl GENİŞ (`grade-evidence-v1`) proyeksiya ilə yaradılır: `compile_safe_projection`
    # kontraktın sxemin ALT-ÇOXLUĞU olmasını tələb edir, ona görə dar `YEKUN_FIELDS`
    # (J5b/J8) və geniş `YEKUN_EVIDENCE_FIELDS` (qiymət sübutu fazası) eyni cədvəldən
    # oxuya bilir.  Dar kontraktla yaratsaq, geniş oxucu
    # `legacy_source_schema_contract_mismatch` ilə çökür.
    ("yekun", YEKUN_EVIDENCE_FIELDS, (), _YEKUN_ROWS, _yekun_values),
    (
        "imthngrscxsblr",
        EXAM_ENTRY_EXIT_FIELDS,
        (),
        _EXAM_ATTEMPT_ROWS,
        _exam_attempt_values,
    ),
    (
        "balvereqi_logs",
        SCORE_SHEET_EXPORT_FIELDS,
        (),
        _SCORE_SHEET_EXPORT_ROWS,
        _score_sheet_export_values,
    ),
)


def _create_full_source_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(f"CREATE USER IF NOT EXISTS '{_READER_USER}'@'%' IDENTIFIED BY '{_READER_PASSWORD}'")
            for table, contract, decoys, rows, values_for in _FULL_TABLES:
                _seed_table(
                    cursor,
                    database=database,
                    table=table,
                    contract=contract,
                    decoys=decoys,
                    rows=rows,
                    values_for=values_for,
                )
            cursor.execute(f"GRANT SELECT ON `{database}`.* TO '{_READER_USER}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            cursor.execute("SET GLOBAL read_only = ON")
    finally:
        root.close()


def _full_policy(**overrides):
    values = {
        "phase_keys": _FULL_PHASE_KEYS,
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.EVIDENCE_MANIFEST,
        "email_trust_manifest_digest": "d" * 64,
        "batch_rows": 500,
        "source_chunk_size": 1_000,
        "max_staged_accounts": _TRUSTED_STUDENTS + _TRUSTED_WORKERS,
        "student_role_name": "student",
        "worker_role_name": "teacher",
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _full_manifest():
    return frozenset(
        {
            *(email_evidence_digest(_full_email("students", index)) for index in range(1, _TRUSTED_STUDENTS + 1)),
            *(email_evidence_digest(_full_email("workers", index)) for index in range(1, _TRUSTED_WORKERS + 1)),
        }
    )


def _full_organization(code):
    owner = get_user_model().objects.create_superuser(
        username=f"rehearsal_full_{code}_actor",
        email=f"rehearsal-full-{code}@example.test",
        password="test-only",
    )
    return (
        Organization.objects.create(
            name=f"Rehearsal Full {code.title()} Organization",
            slug=f"rehearsal-full-{code}-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        ),
        owner,
    )


def _phase_digests(document):
    return {phase["phase_key"]: phase["phase_digest"] for phase in document["deterministic"]["phases"]}


def _issue_histogram(document):
    return {
        (entry["rule_code"], entry["severity"]): entry["count"]
        for entry in document["deterministic"]["issue_histogram"]
    }


def test_disposable_mariadb_full_slice_rehearsal_is_deterministic(monkeypatch, tmp_path):
    """SPEC §8/11 and §10 items 14-15 — two eighteen-phase rehearsals agree
    byte for byte, and a third one that touches accounts deliberately does not.

    ``load_legacy_table_plan`` is patched ONLY with ``_journal_scaled_plan``:
    the disposable source carries the canonical
    31/83/766/2 521/126/3 424/7 816/729 shapes for every batch-backed table, so
    the run's own ``source_row_count`` is still the real 15 496 and every plan
    row-count gate is exercised for real; the narrowing touches nothing but the
    two big journal tables, which no phase declares into ``source_rows``.

    A second physical PostgreSQL database cannot be reached inside one test
    transaction, so — exactly as
    ``test_rehearsal_postgres.test_two_clean_targets_produce_the_same_determinism_digest``
    documents — the two passes run under two INDEPENDENT tenants created before
    either of them, which keeps the pre-run identity baseline identical while
    everything the digest excludes (run pk, tenant pk, timestamps, chain
    digests) still differs.
    """

    port, database = _guarded_endpoint()
    _create_full_source_fixture(port, database)
    opened = []
    try:
        monkeypatch.setattr(phase_a_module, "assert_disposable_rehearsal_target", lambda **_kwargs: _GUARD)
        monkeypatch.setattr(phase_a_module, "load_legacy_table_plan", _journal_scaled_plan)
        first_organization, first_actor = _full_organization("one")
        second_organization, second_actor = _full_organization("two")
        # The activating pass gets its OWN tenant, created up front like the
        # other two, so its pre-run identity baseline is identical to theirs.
        third_organization, third_actor = _full_organization("three")
        report_dir = tmp_path / "full-reports"
        report_dir.mkdir()
        arguments = {
            "settings_object": SimpleNamespace(),
            "policy": _full_policy(),
            "report_dir": str(report_dir),
            "apply_confirmation": connection.settings_dict["NAME"],
            "source_path": _SOURCE_PATH,
            "source_size_bytes": _SOURCE_SIZE_BYTES,
            "email_trust_manifest_digests": _full_manifest(),
            "source_preflight": _preflight,
            "source_factory_builder": _source_factory_builder(port, database, opened),
        }

        first = execute_rehearsal(rehearsal_ordinal=1, organization=first_organization, actor=first_actor, **arguments)

        # V-24 scope yazısı DB-də: bu assert MÜTLƏQ qlobal-vəziyyət bərpasından
        # (aşağıdakı myedu.* silinməsi — kaskadla Membership-ləri də aparır)
        # ƏVVƏL yoxlanmalıdır, əks halda həmişə 0 görər (2026-08-27 insidenti).
        assert (
            Membership.objects.filter(
                organization=first_organization, user__username__startswith="myedu.worker.", scope_unit__isnull=False
            ).count()
            == _TRUSTED_WORKERS
        )

        # J0-J3 hədəf yazıları DB-də: bu assert-lər də MÜTLƏQ qlobal-vəziyyət
        # bərpasından (aşağıdakı myedu.* silinməsi) ƏVVƏL yerləşməlidir —
        # 2026-08-27 insidenti ilə eyni sinif tələ (sonra yoxlansaydı kaskad /
        # sonrakı keçidlər şəkli dəyişə bilərdi).
        period_model = django_apps.get_model("organizations", "AcademicPeriod")
        offering_model = django_apps.get_model("registrar", "CourseOffering")
        scheme_model = django_apps.get_model("registrar", "AssessmentScheme")
        enrollment_model = django_apps.get_model("registrar", "Enrollment")
        lesson_model = django_apps.get_model("registrar", "Lesson")
        periods = period_model.objects.filter(organization=first_organization)
        # J0: 12 fərqli (il, fəsil) cütü yaradılır (12-ci sətir karantindədir);
        # V9: ``is_current`` HEÇ VAXT köçürülmür.
        assert periods.count() == 12
        assert periods.filter(is_current=True).exists() is False
        offerings = offering_model.objects.filter(organization=first_organization)
        # J1 (qrup-başına bölgü, 2026-08): 21 MIGRATED jurnal → 23 offering.
        # 19 jurnal tək qrupludur; 6 (``["3","4"]``) və 7 (``["5","6"]``) isə
        # İKİ qrupludur və hər biri İKİ dilim verir: 19 + 2 + 2 = 23.
        # Köhnə (bölgüsüz) davranışda 6 və 7 eyni (fənn, dövr, group=NULL)
        # açarına düşüb TƏK offering-ə qatlanırdı, ona görə say 20 idi.
        assert offerings.count() == 23
        # Bölgünün ÖZ invariantı: hər dilim ÖZ qrupunu alır — heç iki dilim
        # bir qrupa qatlanmır və qrupsuz (group=NULL) offering ümumiyyətlə
        # yaranmır (``_slice_entry`` qrupu həll olunmayan dilimi karantinə atır).
        assert offerings.values("group").distinct().count() == 23
        assert offerings.filter(group__isnull=True).count() == 0
        # V5/PG: staged üzvlüklər qeyri-aktivdir və ``registrar_guard_active_member``
        # ``grade.input``-lu instructor istinadını rədd edərdi — fixture qəsdən
        # yalnız həll olunmayan teacher_id daşıyır, instructor hər yerdə NULL.
        assert offerings.filter(instructor__isnull=False).exists() is False
        assert scheme_model.objects.filter(organization=first_organization).count() == 23
        # J2: eyni trigger Enrollment-in ``student_id``-si üçün də aktiv üzvlük
        # tələb edir, staged hesablar isə qeyri-aktivdir — ona görə sintetik
        # jurnallar MIGRATED offering-lərdə yalnız naməlum tələbə istinadları
        # daşıyır (42 × ``legacy_journal_student_unresolved``) və heç bir
        # Enrollment yazılmır; materialise yolu sqlite unit dəstində sübutludur.
        assert enrollment_model.objects.filter(organization=first_organization).count() == 0
        lessons = lesson_model.objects.filter(organization=first_organization)
        # J3: 60 sətirdən 54 dərs.  Bir legacy tarix sətri jurnalın HƏR
        # materiallaşmış diliminə təkrarlanır; 48 keçərli sətrin 6-sı çoxqruplu
        # jurnala (6 və 7) düşür və 2 dilimə açılır: 42×1 + 6×2 = 54.
        # Kənarda qalan 12 sətir bölgüdən ƏVVƏLKİ pillədə dayanır (2 dublikat +
        # 5 orphan + 5 yararsız), ona görə jurnal-səviyyə TƏK möhür alır.
        # instructor açılış müəlliminin güzgüsüdür — hamısı NULL.
        assert lessons.count() == 54
        # Bölgünün ikinci invariantı: 23 açılışın HAMISINDA dərs var.
        assert lessons.values("offering_id").distinct().count() == 23
        assert lessons.filter(instructor__isnull=False).exists() is False

        # J4-J6: qeydiyyat yoxdur (yuxarıdakı J2 qeydi) → HEÇ BİR bal xanası
        # yazılmır; J7 isə bitmiş dövrlərin sxemlərini kilidləyir.  Bu assert-lər
        # də MÜTLƏQ qlobal-vəziyyət bərpasından ƏVVƏL olmalıdır (2026-08-27
        # insidenti ilə eyni sinif tələ).
        mark_model = django_apps.get_model("registrar", "LessonMark")
        component_model = django_apps.get_model("registrar", "AssessmentComponent")
        component_score_model = django_apps.get_model("registrar", "ComponentScore")
        final_model = django_apps.get_model("registrar", "FinalGrade")
        resit_model = django_apps.get_model("registrar", "ResitRecord")
        assert mark_model.objects.filter(organization=first_organization).count() == 0
        assert component_model.objects.filter(organization=first_organization).count() == 0
        assert component_score_model.objects.filter(organization=first_organization).count() == 0
        assert final_model.objects.filter(organization=first_organization).count() == 0
        assert resit_model.objects.filter(organization=first_organization).count() == 0
        # J7/V10: hər 23 açılışın sxemi APPROVED + published-dir (bütün sintetik
        # dövrlər 2021-2025-dədir, yəni artıq bitib); CheckConstraint cütü qorunur.
        published = scheme_model.objects.filter(organization=first_organization, is_published=True)
        assert published.count() == 23
        assert published.exclude(approval_status="approved").exists() is False

        # QLOBAL VƏZİYYƏTİN BƏRPASI (2026-08-26 determinizm insidenti): staging
        # QLOBAL auth_user-ə yazır; iki-tenant-eyni-DB yaxınlaşması yalnız
        # qlobal-yazısız siyasətlərdə keçərlidir.  Real istehsalda D5 hər
        # rehearsal-a TƏZƏ disposable baza tələb edir — burada həmin təmizliyi
        # 1-ci pasın staged istifadəçilərini silməklə emulyasiya edirik (adlar
        # və FİN-lər yalnız həmin sətirlərdə idi, kaskadla gedir).
        staged_total = _TRUSTED_STUDENTS + _TRUSTED_WORKERS
        deleted, _detail = get_user_model().objects.filter(username__startswith="myedu.").delete()
        assert deleted >= staged_total

        second = execute_rehearsal(
            rehearsal_ordinal=2, organization=second_organization, actor=second_actor, **arguments
        )

        assert first.status == LegacyMigrationRun.Status.SUCCEEDED
        assert second.status == LegacyMigrationRun.Status.SUCCEEDED

        first_document = json.loads(open(first.report_path, encoding="ascii").read())
        second_document = json.loads(open(second.report_path, encoding="ascii").read())

        # 1) The whole registry ran, in its fixed ascending order.
        assert [phase["phase_key"] for phase in first_document["deterministic"]["phases"]] == list(_FULL_PHASE_KEYS)
        assert [phase["order"] for phase in first_document["deterministic"]["phases"]] == _FULL_PHASE_ORDERS

        # 2) The real accounting totals — 880 structure rows + 6 071 catalogue
        #    rows + 8 545 identity rows; the seven batch-less derived phases
        #    (three identity-derived + four journal) contribute exactly 0 each.
        assert first_document["deterministic"]["totals"]["source_rows"] == _FULL_SOURCE_ROWS == 15_496
        observed = {
            phase["phase_key"]: phase["observed_source_rows"] for phase in first_document["deterministic"]["phases"]
        }
        assert observed == {
            "academic_structure": 880,
            "academic_catalog": 6_071,
            "identity_cohort": 8_545,
            "student_placement": 0,
            "worker_materialisation": 0,
            "sar_materialisation": 0,
            "journal_periods": 0,
            "journal_offerings": 0,
            "journal_enrollments": 0,
            "journal_lessons": 0,
            "journal_marks": 0,
            "journal_components": 0,
            "journal_entry_scores": 0,
            "journal_finals": 0,
            "journal_lock": 0,
            "legacy_grade_facts": 0,
            "journal_reconcile": 0,
            "legacy_grade_artifacts": 0,
        }

        # 3) Determinism across two independent targets.
        assert second.determinism_digest == first.determinism_digest
        assert _phase_digests(second_document) == _phase_digests(first_document)
        assert _issue_histogram(second_document) == _issue_histogram(first_document)
        assert first_document["provenance"]["run_id"] != second_document["provenance"]["run_id"]
        assert first_document["provenance"]["organization_id"] != second_document["provenance"]["organization_id"]

        # 4) The placement phase derived one decision per staged student, and
        #    V-2's admission-year gap stays INFO-only (it never blocks SUCCEEDED).
        placement = next(
            phase for phase in first_document["deterministic"]["phases"] if phase["phase_key"] == "student_placement"
        )
        assert sum(placement["state_counts"].values()) == _TRUSTED_STUDENTS
        assert set(placement["state_counts"]) <= {"record_created", "record_deferred", "record_unresolved"}
        histogram = _issue_histogram(first_document)
        assert first_document["deterministic"]["totals"]["blocking_issue_count"] == 0
        assert all(severity not in ("error", "critical") for (_rule, severity) in histogram)
        # V-2: the admission-year gap is the loudest INFO code and never blocks.
        assert histogram.get(("legacy_record_admission_year_missing", "info"), 0) >= 1

        # 4b) The catalogue accounted for every one of its 6 071 rows and the
        #     SAR phase deferred every student without touching one account.
        catalog = next(
            phase for phase in first_document["deterministic"]["phases"] if phase["phase_key"] == "academic_catalog"
        )
        assert sum(catalog["state_counts"].values()) == _CATALOG_SOURCE_ROWS
        assert set(catalog["state_counts"]) <= {"migrated", "skipped", "quarantined"}
        sar = next(
            phase for phase in first_document["deterministic"]["phases"] if phase["phase_key"] == "sar_materialisation"
        )
        assert sum(sar["state_counts"].values()) == _TRUSTED_STUDENTS
        # V-22/V-25: the worker pass derived one decision per staged worker and,
        # with the activation switch off, wrote ONLY the department scope —
        # every decision is a deferral and no account was touched.
        worker_phase = next(
            phase
            for phase in first_document["deterministic"]["phases"]
            if phase["phase_key"] == "worker_materialisation"
        )
        assert sum(worker_phase["state_counts"].values()) == _TRUSTED_WORKERS
        assert worker_phase["state_counts"].get("worker_materialised", 0) == 0
        assert set(worker_phase["state_counts"]) <= {"worker_materialised", "worker_deferred", "worker_unresolved"}
        # V-24: hazırkı dump-da hər worker department-i mövcuddur — 0 unresolved.
        assert histogram.get(("legacy_worker_department_unresolved", "warning"), 0) == 0
        # V-23: ``inzibati == 1`` yalnız INFO bayrağıdır, rol yüksəltmə yoxdur.
        assert histogram.get(("legacy_worker_administrative_flag", "info"), 0) >= 1
        # 4c) FAZA 3B (J0-J3): dörd jurnal fazasının dəqiq state şəkli — 13
        #     semestr sətri, 30 jurnal (21 MIGRATED / 3 V6 / 6 karantin), 57
        #     qeydiyyat qərarı (56 SKIPPED + 1 karantin) və 60 dərs sətri
        #     (48 + 7 SKIPPED + 5 karantin).
        journal_states = {
            phase["phase_key"]: phase["state_counts"]
            for phase in first_document["deterministic"]["phases"]
            if phase["phase_key"].startswith("journal_")
        }
        assert journal_states == {
            "journal_periods": {"period_materialised": 12, "period_unresolved": 1},
            "journal_offerings": {"offering_materialised": 23, "offering_discarded": 3, "offering_unresolved": 6},
            "journal_enrollments": {"enrollment_skipped": 56, "enrollment_unresolved": 1},
            "journal_lessons": {"lesson_materialised": 54, "lesson_skipped": 7, "lesson_unresolved": 5},
            # J4: 5 jurnal toxunulur — 1 və 2 karantin kodu daşıyır, 6/7 və
            # V6-süzülmüş 3 isə yalnız yazıla bilməyən sətirlər (spec B.6:
            # möhür JURNAL səviyyəsindədir, sətir başına map yoxdur).
            "journal_marks": {"journal_marks_skipped": 3, "journal_marks_unresolved": 2},
            # J5/J6: hər dörd MIGRATED jurnalda karantin kodu var; orphan
            # jurnal isə yalnız SKIPPED-dir.
            "journal_components": {"journal_components_skipped": 1, "journal_components_unresolved": 4},
            # J5b: heç bir yazılış MIGRATED deyil (yuxarıdakı J2 qeydi) → 21
            # materiallaşmış dilimin hamısı üzvsüz, yəni sırf SKIPPED möhürdür.
            "journal_entry_scores": {"journal_entry_scores_skipped": 23},
            "journal_finals": {"journal_finals_skipped": 1, "journal_finals_unresolved": 4},
            # J7: 21 MIGRATED jurnalın hamısının dövrü bitib → hamısı kilidli.
            "journal_lock": {"journal_locked": 23},
            # J8: 3 balans yoxlaması (hamısı delta ilə) + 10 ``yekun`` sətri
            # (qeydiyyat həll olunmur) + 1 karantin xülasəsi.
            # J8 dörd mənbədən möhür yığır: _balance (3, hamısı QUARANTINED),
            # _finals (10 ``yekun`` sətri, QUARANTINED), _coverage
            # (``a-final-coverage``, SKIPPED) və _summary
            # (``a-quarantine-summary``, SKIPPED).  SKIPPED → balanced = 2,
            # QUARANTINED → deviation = 3 + 10 = 13.  Köhnə `1` rəqəmi
            # ``a-final-coverage`` möhürü əlavə olunmamışdan əvvəlkidir
            # (bu, qrup bölgüsü ilə ƏLAQƏSİZ ikinci köhnəlmədir).
            "journal_reconcile": {"reconcile_balanced": 2, "reconcile_deviation": 13},
        }
        legacy_states = {
            phase["phase_key"]: phase["state_counts"]
            for phase in first_document["deterministic"]["phases"]
            if phase["phase_key"].startswith("legacy_grade_")
        }
        assert legacy_states == {
            "legacy_grade_facts": {"legacy_grade_facts_materialised": 83},
            "legacy_grade_artifacts": {"legacy_grade_artifacts_materialised": 2},
        }
        legacy_fact_model = django_apps.get_model("registrar", "LegacyGradeFact")
        legacy_artifact_model = django_apps.get_model("registrar", "LegacyGradeArtifact")
        # İkinci rehearsal sessiya tenant-ını ikinci təşkilata keçirib.  FORCE
        # RLS altında onun 83/2 sübutu görünür, birinci tenant-ın sübutu isə
        # görünməz qalır — bu, data itkisi deyil, gözlənilən izolasiya sübutudur.
        assert legacy_fact_model.objects.filter(organization=second_organization).count() == 83
        assert legacy_artifact_model.objects.filter(organization=second_organization).count() == 2
        assert legacy_fact_model.objects.filter(organization=first_organization).count() == 0
        assert legacy_artifact_model.objects.filter(organization=first_organization).count() == 0

        # Birinci tenant kontekstində simmetrik nəticə alınmalıdır: onun bütün
        # immutable grade evidence-i görünür, ikinci tenant-dakı heç nə sızmır.
        set_rls_tenant(first_organization.pk, local=False)
        assert legacy_fact_model.objects.filter(organization=first_organization).count() == 83
        assert legacy_artifact_model.objects.filter(organization=first_organization).count() == 2
        assert legacy_fact_model.objects.filter(organization=second_organization).count() == 0
        assert legacy_artifact_model.objects.filter(organization=second_organization).count() == 0
        # J-V9(F) uyğunluq cədvəli sətir-başına İNFO kimi + tam issue taksonomiyası.
        assert histogram.get(("legacy_journal_period_created", "info"), 0) == 12
        assert histogram.get(("legacy_journal_period_matched_existing", "info"), 0) == 0
        assert histogram.get(("legacy_journal_period_current_flag", "info"), 0) == 1
        assert histogram.get(("legacy_journal_period_invalid", "warning"), 0) == 1
        assert histogram.get(("legacy_journal_discarded_source", "info"), 0) == 3
        # Bölgüdən sonra bu İNFO jurnal başına DEYİL, DİLİM başına yanır:
        # 6 və 7-nin hər biri 2 dilim → 4.
        assert histogram.get(("legacy_journal_multi_group", "info"), 0) == 4
        # Bölgü birləşməni aradan qaldırdı: 6 və 7 artıq FƏRQLİ qruplara
        # düşür, ona görə eyni açara qatlanmırlar.  ⚠️ Bu assert indi MƏNFİ
        # sübutdur — ``.get(..., 0)`` forması C6 birləşmə yolu kodda tamamilə
        # silinsə də yaşıl qalar; real birləşmə cütü fixture-ə əlavə edilməyib.
        assert histogram.get(("legacy_journal_offering_merged", "info"), 0) == 0
        # V5: instructor həlli QƏSDƏN heç vaxt alınmır (PG active-member qeydi
        # yuxarıda) — bütün 21 materialised + 6 karantin jurnalda İNFO yanır.
        # 23 MIGRATED dilim + 5 jurnal-səviyyə karantin + jurnal 10-un dilimi.
        assert histogram.get(("legacy_journal_instructor_unresolved", "info"), 0) == 29
        assert histogram.get(("legacy_journal_groups_invalid", "warning"), 0) == 2
        assert histogram.get(("legacy_journal_group_unresolved", "warning"), 0) == 1
        assert histogram.get(("legacy_journal_subject_unresolved", "warning"), 0) == 2
        assert histogram.get(("legacy_journal_period_unresolved", "warning"), 0) == 2
        assert histogram.get(("legacy_journal_students_invalid", "warning"), 0) == 1
        assert histogram.get(("legacy_journal_student_unresolved", "warning"), 0) == 42
        assert histogram.get(("legacy_journal_enrollment_orphan", "info"), 0) == 14
        assert histogram.get(("legacy_journal_lesson_orphan", "info"), 0) == 5
        assert histogram.get(("legacy_journal_lesson_duplicate", "info"), 0) == 2
        assert histogram.get(("legacy_journal_lesson_invalid", "warning"), 0) == 5
        # J4 taksonomiyası — issue-lar JURNAL başınadır, sətir başına deyil.
        assert histogram.get(("legacy_journal_mark_orphan", "info"), 0) == 1
        assert histogram.get(("legacy_journal_mark_duplicate", "info"), 0) == 4
        assert histogram.get(("legacy_journal_mark_empty", "info"), 0) == 1
        assert histogram.get(("legacy_journal_mark_score_out_of_range", "warning"), 0) == 1
        assert histogram.get(("legacy_journal_mark_point_unknown", "warning"), 0) == 1
        assert histogram.get(("legacy_journal_mark_enrollment_unresolved", "warning"), 0) == 4
        # Dərs-slot pilləsi bu fixture-də STRUKTUR OLARAQ çatılmazdır: nərdivan
        # əvvəl qeydiyyatı yoxlayır, qeydiyyat isə heç vaxt həll olunmur (PG
        # aktiv-üzvlük qeydi).  Pozuq gün nömrəsi daşıyan 10 sətir buna görə
        # ``enrollment`` rungunda hesaba alınır — amma J8 onları müstəqil
        # şəkildə "oxunmayan" kimi sayır, yəni heç bir sətir səssiz düşmür.
        assert histogram.get(("legacy_journal_mark_lesson_unresolved", "warning"), 0) == 0
        # J-V7: kəsimdən sonrakı 10 arxiv sətri dörd jurnalın üzərinə düşür.
        assert histogram.get(("legacy_journal_archive_overlap", "info"), 0) == 4
        # J5/J6 taksonomiyası.
        assert histogram.get(("legacy_journal_component_orphan", "info"), 0) == 1
        assert histogram.get(("legacy_journal_component_empty", "info"), 0) == 4
        assert histogram.get(("legacy_journal_component_code_unknown", "warning"), 0) == 4
        assert histogram.get(("legacy_journal_component_score_out_of_range", "warning"), 0) == 4
        assert histogram.get(("legacy_journal_component_enrollment_unresolved", "warning"), 0) == 4
        assert histogram.get(("legacy_journal_final_enrollment_unresolved", "warning"), 0) == 4
        assert histogram.get(("legacy_journal_final_orphan", "info"), 0) == 1
        assert histogram.get(("legacy_journal_final_empty", "info"), 0) == 1
        assert histogram.get(("legacy_journal_final_score_out_of_range", "warning"), 0) == 1
        # J-V13 catch-all: pa/wr/ga/ss/ww/ll/rr + ``im`` altındakı ``l``.
        assert histogram.get(("legacy_journal_mark_code_unknown", "warning"), 0) == 4
        # J7/J8 sübutları.
        assert histogram.get(("legacy_journal_lock_applied", "info"), 0) == 23
        assert histogram.get(("legacy_journal_lock_deferred", "info"), 0) == 0
        assert histogram.get(("legacy_journal_reconcile_row_balance", "info"), 0) == 3
        assert histogram.get(("legacy_journal_reconcile_final_unresolved", "warning"), 0) == 10
        assert histogram.get(("legacy_journal_reconcile_quarantine_summary", "info"), 0) == 1

        # ``stage_and_activate`` defaults to False, so nothing was created and
        # the deferral is silent by design — every decision is a deferral.
        assert sar["state_counts"].get("sar_created", 0) == 0
        assert set(sar["state_counts"]) <= {"sar_created", "sar_deferred", "sar_unresolved"}
        # V-18(b): the released-student rung is a SOURCE fact and fires even
        # with the activation switch off.  Student 1 is trusted AND released.
        assert histogram.get(("legacy_sar_departed_student", "info"), 0) >= 1
        assert get_user_model().objects.filter(username__startswith="myedu.", is_active=True).exists() is False
        assert AccountActivationEvidence.objects.count() == 0

        # 5) Regenerating a report from the ledger reproduces its digest —
        #    the batch-less phase's rebuild included (SA-2).  RUN 2 seçilir:
        #    run 1-in staged istifadəçiləri qlobal-bərpa addımında silinib və
        #    rebase düzgün olaraq resume_target_missing ilə fail-closed olur —
        #    bu, evidence-qoruma davranışının özüdür, regen isə run 2-də tam
        #    ekvivalent sübutdur (digest-lər bərabərdir).
        regenerated = execute_rehearsal(
            rehearsal_ordinal=2,  # {1,2} qapısı; eyni-digest overwrite idempotent yoldur
            organization=second_organization,
            actor=second_actor,
            resume_run_id=second.run_id,
            emit_report_only=True,
            **arguments,
        )
        assert regenerated.determinism_digest == second.determinism_digest == first.determinism_digest

        # 6) SA-5 — the activation decision IS the run identity.  A third pass
        #    that differs from the first two ONLY by ``stage_and_activate`` and
        #    its blast-radius cap must produce a different determinism digest;
        #    otherwise two rehearsals with different behaviour could share one
        #    ``transform_version`` and therefore one ledger scope.
        deleted, _again = get_user_model().objects.filter(username__startswith="myedu.").delete()
        assert deleted >= staged_total

        # Ayrı qovluq: bu keçidin digest-i QƏSDƏN fərqlidir və eyni fayla
        # yazılsaydı report-conflict qapısı (düzgün olaraq) bloklardı.
        activation_report_dir = tmp_path / "activation-reports"
        activation_report_dir.mkdir()
        activating_arguments = {
            **arguments,
            "report_dir": str(activation_report_dir),
            "policy": _full_policy(
                stage_and_activate=True, max_activated_accounts=_TRUSTED_STUDENTS + _TRUSTED_WORKERS
            ),
        }
        third = execute_rehearsal(
            rehearsal_ordinal=1, organization=third_organization, actor=third_actor, **activating_arguments
        )

        assert third.status == LegacyMigrationRun.Status.SUCCEEDED
        assert third.determinism_digest != first.determinism_digest
        third_document = json.loads(open(third.report_path, encoding="ascii").read())
        assert third_document["deterministic"]["totals"]["source_rows"] == _FULL_SOURCE_ROWS
        third_sar = next(
            phase for phase in third_document["deterministic"]["phases"] if phase["phase_key"] == "sar_materialisation"
        )
        assert sum(third_sar["state_counts"].values()) == _TRUSTED_STUDENTS
        assert third_sar["state_counts"].get("sar_created", 0) >= 1
        # V-25: worker fazası (order 26) EYNİ kap büdcəsindən əvvəl içir; kap
        # cəmə bərabər olduğundan hər iki qrup tam aktivləşir.
        third_worker = next(
            phase
            for phase in third_document["deterministic"]["phases"]
            if phase["phase_key"] == "worker_materialisation"
        )
        assert sum(third_worker["state_counts"].values()) == _TRUSTED_WORKERS
        assert third_worker["state_counts"].get("worker_materialised", 0) >= 1
        # E-11: activation asserts the registry, never the address — the legacy
        # email is neutralised in the very same transaction.
        activated = get_user_model().objects.filter(username__startswith="myedu.", is_active=True)
        assert (
            activated.count()
            == third_sar["state_counts"]["sar_created"] + third_worker["state_counts"]["worker_materialised"]
        )
        assert activated.filter(profile__email_verified=True).exists() is False
        assert activated.filter(profile__password_change_required=False).exists() is False
        assert AccountActivationEvidence.objects.filter(organization=third_organization).count() == activated.count()

        # §10/15 — the third class of global state this emulation must respect.
        # ``AccountActivationEvidence.organization`` is ``on_delete=PROTECT``, so
        # a tenant that ever activated an account cannot be dropped while its
        # evidence stands — and the evidence itself is APPEND-ONLY at the
        # database level (``accounts_activation_evidence_row_guard_trg`` raises
        # ``accounts_activation_evidence_append_only`` on DELETE).  The only
        # lawful teardown is therefore this test's own transaction rollback; a
        # manual delete-then-drop-tenant sequence is impossible by construction.
        with pytest.raises(DatabaseError) as evidence_exc:
            with transaction.atomic():
                AccountActivationEvidence.objects.filter(organization=third_organization).delete()
        assert "accounts_activation_evidence_append_only" in str(evidence_exc.value)

        # 7) Zero credential or raw-value leakage anywhere in the artifacts.
        document = open(first.report_path, encoding="ascii").read()
        payload = json.dumps(first.payload, ensure_ascii=True, sort_keys=True)
        for forbidden in (
            _CREDENTIAL_VALUE,
            _PRIVATE_VALUE,
            _READER_USER,
            _READER_PASSWORD,
            database,
            _HOST,
            _SOURCE_PATH,
            first_actor.username,
            "password",
            "pin_for_lock",
            _full_email("students", 1),
            "0000001",  # a seeded FİN
        ):
            assert forbidden not in document
            assert forbidden not in payload

        # 8) Every raw source transport was closed by the audited adapter.
        assert opened
        assert all(getattr(source, "closed", True) for source in opened)
    finally:
        # Only the EXTERNAL fixture needs an explicit teardown: every PostgreSQL
        # row — activation evidence included — goes away with the test
        # transaction's rollback, which is the only way an append-only table can
        # ever be cleaned up (see the §10/15 note above).
        _drop_source_fixture(port, database)
