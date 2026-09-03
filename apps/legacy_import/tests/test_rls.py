"""PostgreSQL RLS və DB-level legacy ledger integrity testləri."""

import os
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.models.signals import post_save
from django.utils import timezone

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityMapVersion,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.versioning import ensure_initial_version
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

User = get_user_model()
SHA_A = "a" * 64
SHA_B = "b" * 64

pytestmark = pytest.mark.postgres


def _is_postgresql():
    return connection.vendor == "postgresql"


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enable_rls(organization_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", organization_id)
    _set("app.current_user_id", "")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE rls_app_role")


# PostgreSQL rolları KLASTER səviyyəsindədir (DB-yə bağlı deyil): pytest-xdist
# worker-ləri paralel işləyəndə eyni adlı rol yarat/sil toqquşur (başqa
# worker-in DB-sindəki GRANT DROP ROLE-u bloklayır). Ad worker-ə görə ayrılır.
_PROBE_ROLE = "ems_guard_probe" + os.environ.get("PYTEST_XDIST_WORKER", "")


def _drop_probe_role(cursor):
    cursor.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_PROBE_ROLE}') THEN
                DROP OWNED BY {_PROBE_ROLE};
                DROP ROLE {_PROBE_ROLE};
            END IF;
        END
        $$
        """)


@contextmanager
def _nonsuper_probe_role(tables):
    """TRUNCATE guard-larını qeyri-superuser rol altında yoxlamaq üçün müvəqqəti rol.

    Guard funksiyaları session_user-in superuser olub-olmadığına baxır
    (superuser trigger-i onsuz da DROP edə bilər). Test bağlantısı superuser
    olduğu üçün guard-a çatmaq üçün SET SESSION AUTHORIZATION lazımdır —
    SET ROLE session_user-i dəyişmir.
    """
    with connection.cursor() as cursor:
        _drop_probe_role(cursor)
        cursor.execute(f"CREATE ROLE {_PROBE_ROLE}")
        cursor.execute(f"GRANT TRUNCATE ON TABLE {', '.join(tables)} TO {_PROBE_ROLE}")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET SESSION AUTHORIZATION")
            _drop_probe_role(cursor)


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    if not _is_postgresql():
        yield
        return
    _set("app.bypass_rls", "on")
    _set("app.current_org_id", "")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


def _make_organization(code):
    owner = User.objects.create_user(
        username=f"legacy_rls_owner_{code}",
        email=f"legacy-rls-{code}@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        return Organization.objects.create(
            name=f"Legacy RLS Org {code}",
            slug=f"legacy-rls-org-{code}",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)


def _make_run(organization, source_system, transform_version="transform-v1"):
    run = LegacyMigrationRun.objects.create(
        organization=organization,
        source_system=source_system,
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=1,
        schema_version="legacy-v1",
        transform_version=transform_version,
        mode=LegacyMigrationRun.Mode.REHEARSAL,
    )
    LegacyMigrationRun.objects.filter(pk=run.pk).update(
        status=LegacyMigrationRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    run.refresh_from_db()
    return run


def _make_map(run, legacy_pk="1001"):
    entity_map = LegacyEntityMap.objects.create(
        organization=run.organization,
        source_system=run.source_system,
        entity_type="student",
        legacy_pk=legacy_pk,
        source_row_hash=SHA_B,
        transform_version=run.transform_version,
        target_model_label="auth.user",
        target_pk="42",
        created_run=run,
        state=LegacyEntityMap.State.MIGRATED,
    )
    version = ensure_initial_version(entity_map)
    LegacyEntityObservation.objects.create(
        organization=run.organization,
        run=run,
        entity_map=entity_map,
        map_version=version,
        source_row_hash=entity_map.source_row_hash,
        transform_version=entity_map.transform_version,
        target_model_label=entity_map.target_model_label,
        target_pk=entity_map.target_pk,
        state=entity_map.state,
        reconciliation_status=entity_map.reconciliation_status,
    )
    return entity_map


def _make_issue(run, entity_map):
    return LegacyMigrationIssue.objects.create(
        organization=run.organization,
        run=run,
        entity_map=entity_map,
        source_table="students",
        entity_type=entity_map.entity_type,
        legacy_pk=entity_map.legacy_pk,
        rule_code="missing-fin",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )


@pytest.fixture()
def two_org_ledgers():
    if not _is_postgresql():
        pytest.skip("legacy import RLS tests require PostgreSQL")
    org_a = _make_organization("a")
    org_b = _make_organization("b")
    run_a = _make_run(org_a, "legacy_a")
    run_b = _make_run(org_b, "legacy_b")
    map_a = _make_map(run_a, "1001")
    map_b = _make_map(run_b, "2001")
    issue_a = _make_issue(run_a, map_a)
    issue_b = _make_issue(run_b, map_b)
    observation_a = LegacyEntityObservation.objects.get(run=run_a, entity_map=map_a)
    observation_b = LegacyEntityObservation.objects.get(run=run_b, entity_map=map_b)
    version_a = LegacyEntityMapVersion.objects.get(entity_map=map_a, version_number=1)
    version_b = LegacyEntityMapVersion.objects.get(entity_map=map_b, version_number=1)
    return (
        org_a,
        org_b,
        run_a,
        run_b,
        map_a,
        map_b,
        issue_a,
        issue_b,
        observation_a,
        observation_b,
        version_a,
        version_b,
    )


def test_rls_isolates_all_control_plane_tables(two_org_ledgers):
    org_a, _org_b, *_rows = two_org_ledgers
    _enable_rls(org_a.pk)

    assert LegacyMigrationRun.objects.count() == 1
    assert LegacyEntityMap.objects.count() == 1
    assert LegacyEntityObservation.objects.count() == 1
    assert LegacyMigrationIssue.objects.count() == 1
    assert LegacyEntityMapVersion.objects.count() == 1
    assert set(LegacyMigrationRun.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_rls_missing_tenant_context_denies_all(two_org_ledgers):
    _enable_rls("")

    assert LegacyMigrationRun.objects.count() == 0
    assert LegacyEntityMap.objects.count() == 0
    assert LegacyEntityObservation.objects.count() == 0
    assert LegacyMigrationIssue.objects.count() == 0
    assert LegacyEntityMapVersion.objects.count() == 0


def test_rls_rejects_cross_tenant_insert(two_org_ledgers):
    org_a, org_b, *_rows = two_org_ledgers
    _enable_rls(org_a.pk)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _make_run(org_b, "forged_source")


@pytest.mark.parametrize("scenario", ["source", "organization"])
def test_map_trigger_rejects_cross_scope_and_source(two_org_ledgers, scenario):
    org_a, _org_b, run_a, run_b, *_rows = two_org_ledgers
    created_run = run_a if scenario == "source" else run_b
    source_system = "wrong_source" if scenario == "source" else run_b.source_system

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.create(
                organization=org_a,
                source_system=source_system,
                entity_type="student",
                legacy_pk=f"3001-{scenario}",
                source_row_hash=SHA_A,
                transform_version="transform-v1",
                created_run=created_run,
                state=LegacyEntityMap.State.QUARANTINED,
            )


def test_issue_trigger_rejects_mismatched_map_identity(two_org_ledgers):
    org_a, _org_b, run_a, _run_b, _map_a, map_b, *_issues = two_org_ledgers

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.create(
                organization=org_a,
                run=run_a,
                entity_map=map_b,
                source_table="students",
                entity_type="student",
                legacy_pk=map_b.legacy_pk,
                rule_code="cross-scope-map",
                severity=LegacyMigrationIssue.Severity.CRITICAL,
                payload_digest=SHA_B,
            )


@pytest.mark.parametrize("mismatch", ["entity_type", "legacy_pk"])
def test_issue_trigger_rejects_same_scope_wrong_identity(two_org_ledgers, mismatch):
    org_a, _org_b, run_a, _run_b, *_rows = two_org_ledgers
    other_map = _make_map(run_a, "9001")
    entity_type = "worker" if mismatch == "entity_type" else other_map.entity_type
    legacy_pk = "different-key" if mismatch == "legacy_pk" else other_map.legacy_pk

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.create(
                organization=org_a,
                run=run_a,
                entity_map=other_map,
                source_table="students",
                entity_type=entity_type,
                legacy_pk=legacy_pk,
                rule_code=f"wrong-{mismatch}",
                severity=LegacyMigrationIssue.Severity.CRITICAL,
                payload_digest=SHA_B,
            )


def test_map_trigger_requires_run_transform_version_on_insert_and_update(two_org_ledgers):
    org_a, _org_b, run_a, _run_b, map_a, *_rows = two_org_ledgers

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.create(
                organization=org_a,
                source_system=run_a.source_system,
                entity_type="student",
                legacy_pk="transform-insert",
                source_row_hash=SHA_A,
                transform_version="different-transform",
                created_run=run_a,
                state=LegacyEntityMap.State.QUARANTINED,
            )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.filter(pk=map_a.pk).update(transform_version="different-transform")


def test_map_trigger_preserves_canonical_identity_across_transform_versions(two_org_ledgers):
    org_a, _org_b, run_a, _run_b, map_a, *_rows = two_org_ledgers
    next_run = _make_run(org_a, run_a.source_system, transform_version="transform-v2")

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.filter(pk=map_a.pk).update(
                created_run=next_run,
                transform_version=next_run.transform_version,
            )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _make_map(next_run, map_a.legacy_pk)

    map_a.refresh_from_db()
    assert map_a.created_run_id == run_a.pk
    assert LegacyEntityMap.objects.filter(legacy_pk=map_a.legacy_pk).count() == 1
    assert LegacyEntityObservation.objects.filter(entity_map=map_a).count() == 1


def test_map_trigger_rejects_cross_scope_on_update(two_org_ledgers):
    _org_a, _org_b, _run_a, run_b, map_a, *_rows = two_org_ledgers

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.filter(pk=map_a.pk).update(created_run=run_b)


def test_issue_trigger_rejects_mismatched_map_on_update(two_org_ledgers):
    _org_a, _org_b, _run_a, _run_b, _map_a, map_b, issue_a, *_rows = two_org_ledgers

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.filter(pk=issue_a.pk).update(entity_map=map_b)


def test_observation_trigger_rejects_cross_scope_and_mutation(two_org_ledgers):
    org_a, org_b, run_a, _run_b, map_a, *_rows = two_org_ledgers
    observation = LegacyEntityObservation.objects.get(run=run_a, entity_map=map_a)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityObservation.objects.create(
                organization=org_b,
                run=run_a,
                entity_map=map_a,
                map_version=LegacyEntityMapVersion.objects.get(entity_map=map_a, version_number=1),
                source_row_hash=map_a.source_row_hash,
                transform_version=map_a.transform_version,
                target_model_label=map_a.target_model_label,
                target_pk=map_a.target_pk,
                state=map_a.state,
                reconciliation_status=map_a.reconciliation_status,
            )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityObservation.objects.filter(pk=observation.pk).update(source_row_hash=SHA_A)


def test_restricted_role_cannot_truncate_ledger_tables(two_org_ledgers):
    org_a, _org_b, *_rows = two_org_ledgers
    tables = [
        "legacy_import_legacymigrationrun",
        "legacy_import_legacyentitymap",
        "legacy_import_legacyentityobservation",
        "legacy_import_legacymigrationissue",
        "legacy_import_legacyentitymapversion",
    ]
    _enable_rls(org_a.pk)

    with connection.cursor() as cursor:
        for table in tables:
            for privilege in ("TRUNCATE", "REFERENCES", "TRIGGER"):
                cursor.execute(
                    "SELECT has_table_privilege('rls_app_role', %s, %s)",
                    [f"public.{table}", privilege],
                )
                assert cursor.fetchone() == (False,)
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cursor.execute(
                    "SELECT has_table_privilege('rls_app_role', %s, %s)",
                    [f"public.{table}", privilege],
                )
                assert cursor.fetchone() == (True,)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE TABLE {', '.join(tables)}")

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    _set("app.bypass_rls", "on")
    assert LegacyMigrationRun.objects.count() == 2
    assert LegacyEntityMap.objects.count() == 2
    assert LegacyEntityObservation.objects.count() == 2
    assert LegacyMigrationIssue.objects.count() == 2
    assert LegacyEntityMapVersion.objects.count() == 2


def test_nonsuper_role_cannot_truncate_ledger_tables(two_org_ledgers):
    tables = [
        "legacy_import_legacymigrationrun",
        "legacy_import_legacyentitymap",
        "legacy_import_legacyentityobservation",
        "legacy_import_legacymigrationissue",
        "legacy_import_legacyentitymapversion",
        # run-a FK ilə bağlı batch cədvəli də siyahıda olmalıdır ki, TRUNCATE
        # FK xətasına yox, guard trigger-inə çatsın.
        "legacy_import_legacyimportbatch",
    ]
    expected_triggers = {
        "legacy_import_run_no_truncate",
        "legacy_import_map_no_truncate",
        "legacy_import_observation_no_truncate",
        "legacy_import_issue_no_truncate",
        "legacy_import_version_no_truncate",
        "legacy_import_batch_no_truncate",
    }

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname = ANY(%s)",
            [sorted(expected_triggers)],
        )
        assert {row[0] for row in cursor.fetchall()} == expected_triggers

    with _nonsuper_probe_role(tables):
        with connection.cursor() as cursor:
            # Deferred FK event-lərini boşalt ki, PostgreSQL guard trigger-inə çatsın.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(DatabaseError, match="TRUNCATE edilə bilməz"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"SET SESSION AUTHORIZATION {_PROBE_ROLE}")
                    cursor.execute(f"TRUNCATE TABLE {', '.join(tables)}")

    assert LegacyMigrationRun.objects.count() == 2
    assert LegacyEntityMap.objects.count() == 2
    assert LegacyEntityObservation.objects.count() == 2
    assert LegacyMigrationIssue.objects.count() == 2
    assert LegacyEntityMapVersion.objects.count() == 2


@pytest.mark.parametrize(
    ("table", "row_index"),
    [
        ("legacy_import_legacymigrationrun", 2),
        ("legacy_import_legacyentitymap", 4),
        ("legacy_import_legacymigrationissue", 6),
        ("legacy_import_legacyentityobservation", 8),
        ("legacy_import_legacyentitymapversion", 10),
    ],
)
def test_delete_guard_rejects_direct_sql_even_with_bypass(two_org_ledgers, table, row_index):
    row = two_org_ledgers[row_index]

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table} WHERE id = %s", [row.pk])

    assert row.__class__.objects.filter(pk=row.pk).exists()
