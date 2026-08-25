"""Real-source rehearsal conformance (SPEC §15.3/56).

Written but NEVER run by the implementer (coordination note N5).  It opts in
only when the caller provides BOTH a guarded disposable MariaDB endpoint and a
PostgreSQL target, and it drops everything it created in ``finally``.

Two things are deliberately stubbed even here: the 2.14 GB snapshot preflight
(the file is not part of the repository) and the disposable-target interlock
(the CI PostgreSQL database carries no ``ALTER DATABASE … SET
emsarena.rehearsal_target`` marker).  The real interlock is proven separately by
``test_rehearsal_postgres.test_target_guard_reads_real_disposable_marker``.
"""

import json
import os
import re
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection

import pymysql
import pytest

from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services import rehearsal_phase_a as phase_a_module
from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
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
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256
from apps.legacy_import.tests.test_rehearsal_identity_phase import _plan
from apps.organizations.models import Organization
from core.constants import OrganizationType

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
