"""Historical fixtures retain real DDL and never flush ordinary worker seeds."""

import unittest
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.migrations.exceptions import NodeNotFoundError
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

import pytest

from tests.historical_migration_case import HistoricalDatabase, HistoricalMigrationTestCase

pytestmark = pytest.mark.postgres
TARGET = ("contenttypes", "0001_initial")


def _worker_seed_snapshot():
    profile = apps.get_model("accounts", "UserProfile")
    return (
        tuple(get_user_model().objects.order_by("id").values_list("id", "is_active")),
        tuple(profile.objects.order_by("user_id").values_list("user_id", "organization_id")),
    )


def _assert_database_dropped(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT FROM pg_database WHERE datname = %s)", [name])
        assert cursor.fetchone() == (False,)


@contextmanager
def _probe_worker_database():
    # Class-scoped connection isolation; shared fixtures are never patched.
    original_name = connection.settings_dict["NAME"]
    assert original_name.startswith("test_")
    assert not connection.in_atomic_block
    assert connection.get_autocommit()
    before = _worker_seed_snapshot()
    clone_source = connection.settings_dict.get("TEST", {}).get("TEMPLATE") or original_name
    assert clone_source == "ems_test_template" or clone_source.startswith("test_")
    probe_name = "test_hist_fixture_probe_" + uuid.uuid4().hex
    created = False
    connection.close()
    try:
        with connection._nodb_cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE {connection.ops.quote_name(probe_name)} "
                f"TEMPLATE {connection.ops.quote_name(clone_source)}"
            )
        created = True
        connection.settings_dict["NAME"] = probe_name
        yield
    finally:
        connection.close()
        connection.settings_dict["NAME"] = original_name
        if created:
            with connection._nodb_cursor() as cursor:
                cursor.execute(f"DROP DATABASE {connection.ops.quote_name(probe_name)} WITH (FORCE)")
        assert _worker_seed_snapshot() == before


class _ProbeWorkerCase(TransactionTestCase):
    @classmethod
    def _fixture_setup(cls):
        cls._worker_scope = _probe_worker_database()
        cls._worker_scope.__enter__()

    def _fixture_teardown(self):
        type(self)._worker_scope.__exit__(None, None, None)
        type(self)._worker_scope = None


class HistoricalDatabaseTests(_ProbeWorkerCase):

    def test_success_preserves_worker_profiles_and_real_historical_schema(self):
        user = get_user_model().objects.create_user(id=9_900_001, username="historical-helper-worker-profile")
        profile = apps.get_model("accounts", "UserProfile").objects.get(user_id=user.pk)
        profile.patronymic = "retained-worker-profile-proof"
        profile.save(update_fields=["patronymic"])
        original_name = connection.settings_dict["NAME"]
        try:
            before = _worker_seed_snapshot()
            with HistoricalDatabase(TARGET) as historical:
                name = historical.owned_name
                assert name.startswith(HistoricalDatabase.prefix)
                assert name != original_name
                assert connection.settings_dict["NAME"] == name
                assert set(MigrationRecorder(connection).applied_migrations()) == {TARGET}
                with connection.cursor() as cursor:
                    tables = set(connection.introspection.table_names(cursor))
                assert "django_content_type" in tables
                assert "accounts_userprofile" not in tables
            assert connection.settings_dict["NAME"] == original_name
            assert _worker_seed_snapshot() == before
            profile.refresh_from_db()
            assert profile.patronymic == "retained-worker-profile-proof"
            _assert_database_dropped(name)
            for should_fail in (False, True):
                captured = []

                class Probe(HistoricalMigrationTestCase):
                    historical_migration_target = TARGET
                    captured_names = captured
                    expected_failure = should_fail

                    def test_owned_case(self):
                        self.captured_names.append(connection.settings_dict["NAME"])
                        self.assertTrue(self.captured_names[-1].startswith(HistoricalDatabase.prefix))
                        if self.expected_failure:
                            self.fail("intentional_owned_case_failure")

                result = unittest.TestResult()
                unittest.TestSuite([Probe("test_owned_case")]).run(result)
                assert result.testsRun == 1
                assert len(result.failures) == int(should_fail)
                assert result.errors == []
                assert connection.settings_dict["NAME"] == original_name
                assert _worker_seed_snapshot() == before
                profile.refresh_from_db()
                assert profile.patronymic == "retained-worker-profile-proof"
                _assert_database_dropped(captured[0])
        finally:
            # The local probe worker is discarded by the fixture, including this probe user.
            assert connection.settings_dict["NAME"] == original_name

    def test_failure_restores_worker_profiles_and_drops_only_owned_database(self):
        before = _worker_seed_snapshot()
        original_name = connection.settings_dict["NAME"]
        historical = HistoricalDatabase(TARGET)
        with pytest.raises(RuntimeError, match="intentional_case_failure"):
            with historical:
                raise RuntimeError("intentional_case_failure")
        assert connection.settings_dict["NAME"] == original_name
        assert _worker_seed_snapshot() == before
        _assert_database_dropped(historical.owned_name)

    def test_setup_failure_also_drops_owned_database_and_restores_worker(self):
        before = _worker_seed_snapshot()
        original_name = connection.settings_dict["NAME"]
        historical = HistoricalDatabase(("contenttypes", "9999_missing"))
        with pytest.raises(NodeNotFoundError):
            historical.__enter__()
        assert connection.settings_dict["NAME"] == original_name
        assert _worker_seed_snapshot() == before
        _assert_database_dropped(historical.owned_name)

    def test_active_transaction_is_rejected_before_database_creation(self):
        historical = HistoricalDatabase(TARGET)
        original_name = connection.settings_dict["NAME"]
        with transaction.atomic():
            with pytest.raises(RuntimeError, match="outside_transaction_required"):
                historical.__enter__()
        assert historical.owned_name is None
        assert connection.settings_dict["NAME"] == original_name

    def test_manual_begin_is_rejected_without_rolling_back_worker_transaction(self):
        historical = HistoricalDatabase(TARGET)
        original_name = connection.settings_dict["NAME"]
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                with pytest.raises(RuntimeError, match="outside_transaction_required"):
                    historical.__enter__()
                assert historical.owned_name is None
                assert connection.settings_dict["NAME"] == original_name
                assert int(connection.connection.info.transaction_status) == 2
            finally:
                cursor.execute("ROLLBACK")

    def test_sequence_reset_uses_historical_tables_and_preserves_migration_recorder(self):
        with HistoricalDatabase(TARGET) as historical:
            with connection.cursor() as cursor:
                cursor.execute("SELECT setval(pg_get_serial_sequence('django_content_type', 'id'), 100, true)")
                cursor.execute("SELECT last_value, is_called FROM django_migrations_id_seq")
                recorder_before = cursor.fetchone()
            historical.reset_sequences()
            with connection.cursor() as cursor:
                cursor.execute("SELECT last_value, is_called FROM django_content_type_id_seq")
                assert cursor.fetchone() == (1, False)
                cursor.execute("SELECT last_value, is_called FROM django_migrations_id_seq")
                assert cursor.fetchone() == recorder_before
            assert set(MigrationRecorder(connection).applied_migrations()) == {TARGET}

    def test_partial_ddl_cannot_be_hidden_by_discarding_the_owned_database(self):
        with HistoricalDatabase(TARGET) as historical:
            historical.assert_recorded_schema()
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE django_content_type ADD COLUMN unexpected_partial integer")
            with pytest.raises(AssertionError, match="historical_migration_schema_mismatch:django_content_type"):
                historical.assert_recorded_schema()


@pytest.mark.parametrize(
    ("vendor", "name", "code"),
    [
        ("sqlite", "test_worker", "postgresql_required"),
        ("postgresql", "production", "worker_test_database_required"),
        ("postgresql", "ems_prod_1027", "worker_test_database_required"),
        ("postgresql", HistoricalDatabase.prefix + "nested", "worker_test_database_required"),
    ],
)
def test_unsafe_connection_never_connects_or_creates_database(vendor, name, code):
    fake = SimpleNamespace(vendor=vendor, settings_dict={"NAME": name}, get_autocommit=Mock(), _nodb_cursor=Mock())
    with patch("tests.historical_migration_case.connection", fake):
        with pytest.raises(RuntimeError, match=code):
            HistoricalDatabase(TARGET).__enter__()
    fake.get_autocommit.assert_not_called()
    fake._nodb_cursor.assert_not_called()
