"""PostgreSQL defense-in-depth checks for scalable batch accounting."""

from contextlib import contextmanager

from django.db import DatabaseError, connection, transaction
from django.db.models.signals import post_save
from django.utils import timezone

import pytest

from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services.batch_accounting import record_batch
from apps.legacy_import.services.ledger import create_run, start_run
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64

pytestmark = [pytest.mark.postgres, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _postgresql_only():
    if connection.vendor != "postgresql":
        pytest.skip("Batch DB guards require PostgreSQL")


def _allow(**_kwargs):
    return True


@pytest.fixture()
def two_organizations(django_user_model):
    actor = django_user_model.objects.create_user(
        username="batch_pg_actor",
        email="batch-pg-actor@example.test",
        password="test-only",
    )
    other_actor = django_user_model.objects.create_user(
        username="batch_pg_other_actor",
        email="batch-pg-other-actor@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name="Batch PG Organization",
            slug="batch-pg-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )
        other_organization = Organization.objects.create(
            name="Batch PG Other Organization",
            slug="batch-pg-other-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=other_actor,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, other_organization, actor, other_actor


def _running_run(
    organization,
    actor,
    *,
    rows=2,
    accounting_mode="batch",
    source_system="myedu_mariadb",
):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system=source_system,
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=rows,
        schema_version="schema-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=accounting_mode,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _direct_batch(run, actor, **overrides):
    values = {
        "organization": run.organization,
        "run": run,
        "recorded_by": actor,
        "source_table": "students",
        "entity_type": "student",
        "sequence": 1,
        "first_legacy_pk": 10,
        "last_legacy_pk": 11,
        "source_row_count": 2,
        "migrated_count": 1,
        "skipped_count": 0,
        "quarantined_count": 1,
        "contract_fingerprint": SHA_A,
        "source_digest": SHA_B,
        "classification_digest": SHA_C,
        "target_digest": SHA_D,
        "previous_chain_digest": "",
        "chain_digest": SHA_A,
    }
    values.update(overrides)
    return LegacyImportBatch.objects.create(**values)


def _rejects(write):
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            write()


_PROBE_ROLE = "ems_guard_probe"


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
    """Temporary non-superuser role for probing the TRUNCATE guard.

    The guard waves superusers through (they could DROP the trigger anyway)
    and checks session_user, which SET ROLE does not change -- hence
    SET SESSION AUTHORIZATION from the superuser test connection.
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


def test_owner_raw_update_delete_truncate_and_mode_mutation_are_blocked(two_organizations):
    organization, _other, actor, _other_actor = two_organizations
    run = _running_run(organization, actor, source_system="myedu_mariadb_batch")
    batch = _direct_batch(run, actor)

    def raw(sql, params=()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)

    _rejects(
        lambda: raw(
            "UPDATE legacy_import_legacyimportbatch SET chain_digest = %s WHERE id = %s",
            [SHA_B, batch.pk],
        )
    )
    _rejects(lambda: raw("DELETE FROM legacy_import_legacyimportbatch WHERE id = %s", [batch.pk]))

    def truncate_as_probe():
        with connection.cursor() as cursor:
            cursor.execute(f"SET SESSION AUTHORIZATION {_PROBE_ROLE}")
            cursor.execute("TRUNCATE TABLE legacy_import_legacyimportbatch")

    with _nonsuper_probe_role(["legacy_import_legacyimportbatch"]):
        with connection.cursor() as cursor:
            # Flush deferred FK events so PostgreSQL reaches the BEFORE TRUNCATE guard.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        _rejects(truncate_as_probe)
    _rejects(
        lambda: raw(
            "UPDATE legacy_import_legacymigrationrun SET accounting_mode = 'row' WHERE id = %s",
            [run.pk],
        )
    )

    batch.refresh_from_db()
    run.refresh_from_db()
    assert batch.chain_digest == SHA_A
    assert run.accounting_mode == LegacyMigrationRun.AccountingMode.BATCH


def test_database_rejects_row_mode_cross_org_inactive_actor_and_zero_pk(two_organizations, django_user_model):
    organization, other_organization, actor, _other_actor = two_organizations
    row_run = _running_run(
        organization,
        actor,
        accounting_mode=LegacyMigrationRun.AccountingMode.ROW,
    )
    _rejects(lambda: _direct_batch(row_run, actor))

    run = _running_run(organization, actor, source_system="myedu_mariadb_batch")
    _rejects(lambda: _direct_batch(run, actor, organization=other_organization))

    inactive = django_user_model.objects.create_user(
        username="batch_pg_inactive",
        email="batch-pg-inactive@example.test",
        password="test-only",
        is_active=False,
    )
    _rejects(lambda: _direct_batch(run, inactive))
    _rejects(
        lambda: _direct_batch(
            run,
            actor,
            source_table="zero_pk_source",
            first_legacy_pk=0,
            last_legacy_pk=0,
            source_row_count=1,
            migrated_count=1,
            quarantined_count=0,
        )
    )
    assert not LegacyImportBatch.objects.exists()


def test_database_rejects_sequence_overlap_entity_and_contract_drift(two_organizations):
    organization, _other, actor, _other_actor = two_organizations
    run = _running_run(organization, actor, rows=4)
    first = _direct_batch(run, actor)

    _rejects(
        lambda: _direct_batch(
            run,
            actor,
            source_table="workers",
            entity_type="worker",
            sequence=2,
            first_legacy_pk=20,
            last_legacy_pk=20,
            source_row_count=1,
            migrated_count=1,
            quarantined_count=0,
            previous_chain_digest=first.chain_digest,
        )
    )
    common = {
        "sequence": 2,
        "first_legacy_pk": 20,
        "last_legacy_pk": 20,
        "source_row_count": 1,
        "migrated_count": 1,
        "quarantined_count": 0,
        "previous_chain_digest": first.chain_digest,
        "chain_digest": SHA_B,
    }
    _rejects(lambda: _direct_batch(run, actor, **{**common, "first_legacy_pk": 11}))
    _rejects(lambda: _direct_batch(run, actor, **common, entity_type="worker"))
    _rejects(lambda: _direct_batch(run, actor, **common, contract_fingerprint=SHA_D))
    assert list(LegacyImportBatch.objects.values_list("pk", flat=True)) == [first.pk]


def test_database_terminal_transition_requires_explicit_batch_sums(two_organizations):
    organization, _other, actor, _other_actor = two_organizations
    run = _running_run(organization, actor)
    _direct_batch(run, actor)

    def finish(*, migrated, quarantined):
        return LegacyMigrationRun.objects.filter(pk=run.pk).update(
            status=LegacyMigrationRun.Status.SUCCEEDED,
            finished_at=timezone.now(),
            migrated_count=migrated,
            skipped_count=0,
            quarantined_count=quarantined,
            failure_code="",
        )

    _rejects(lambda: finish(migrated=0, quarantined=0))
    assert finish(migrated=1, quarantined=1) == 1
    run.refresh_from_db()
    assert run.status == LegacyMigrationRun.Status.SUCCEEDED


def test_force_rls_missing_context_and_cross_tenant_write_are_fail_closed(two_organizations):
    organization, other_organization, actor, other_actor = two_organizations
    run = _running_run(organization, actor)
    other_run = _running_run(other_organization, other_actor)
    _direct_batch(run, actor)
    _direct_batch(other_run, other_actor)

    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
        cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(organization.pk)])
        cursor.execute("SET LOCAL ROLE rls_app_role")
    try:
        assert LegacyImportBatch.objects.count() == 1
        allowed = _direct_batch(run, actor, source_table="rls_allowed")
        assert allowed.organization_id == organization.pk
        assert LegacyImportBatch.objects.count() == 2
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_org_id', '', true)")
        assert LegacyImportBatch.objects.count() == 0
        _rejects(lambda: _direct_batch(run, actor, source_table="missing_context"))

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(organization.pk)])
        _rejects(lambda: _direct_batch(other_run, other_actor, source_table="cross_tenant"))
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def test_restricted_role_privileges_and_trigger_functions_are_hardened():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'public.legacy_import_legacyimportbatch'::regclass"
        )
        rls_flags = cursor.fetchone()
        cursor.execute(
            "SELECT p.proname, p.prosecdef, p.proconfig, "
            "has_function_privilege('rls_app_role', p.oid, 'EXECUTE'), "
            "EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl "
            "WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE') "
            "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
            "AND p.proname = ANY(%s)",
            [["legacy_import_batch_integrity_guard", "legacy_import_run_identity_guard"]],
        )
        functions = cursor.fetchall()
        cursor.execute(
            "SELECT has_table_privilege('rls_app_role', %s, privilege) "
            "FROM unnest(%s::text[]) AS privileges(privilege)",
            [
                "public.legacy_import_legacyimportbatch",
                ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"],
            ],
        )
        privileges = [row[0] for row in cursor.fetchall()]

    assert rls_flags == (True, True)
    assert {row[0] for row in functions} == {
        "legacy_import_batch_integrity_guard",
        "legacy_import_run_identity_guard",
    }
    for _name, security_definer, config, restricted_execute, public_execute in functions:
        assert security_definer is True
        assert "search_path=pg_catalog, public" in config
        assert restricted_execute is False
        assert public_execute is False
    assert privileges == [True, True, False, False, False, False, False]


def test_service_batch_insert_remains_compatible_with_database_guards(two_organizations):
    organization, _other, actor, _other_actor = two_organizations
    run = _running_run(organization, actor)

    batch = record_batch(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type="student",
        sequence=1,
        first_legacy_pk=10,
        last_legacy_pk=11,
        migrated_count=1,
        skipped_count=0,
        quarantined_count=1,
        contract_fingerprint=SHA_A,
        source_digest=SHA_B,
        classification_digest=SHA_C,
        target_digest=SHA_D,
    )

    assert batch.run_id == run.pk
    assert LegacyImportBatch.objects.count() == 1
