"""Real historical PostgreSQL schemas without rewinding a shared worker database."""

import uuid
from unittest import SkipTest

from django.conf import settings
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class HistoricalDatabase:
    """Own one empty database and restore the worker connection on every exit."""

    prefix = "test_ems_historical_case_"

    def __init__(self, target):
        self.target = target
        self.original_name = None
        self.owned_name = None
        self.created = False

    def _guard(self):
        if connection.vendor != "postgresql":
            raise RuntimeError("historical_migration_postgresql_required")
        name = connection.settings_dict.get("NAME")
        if not isinstance(name, str) or not name.startswith("test_") or name.startswith(self.prefix):
            raise RuntimeError("historical_migration_worker_test_database_required")
        if connection.in_atomic_block or connection.needs_rollback or not connection.get_autocommit():
            raise RuntimeError("historical_migration_outside_transaction_required")
        raw = connection.connection
        status = getattr(getattr(raw, "info", None), "transaction_status", None)
        if status is None or int(status) != 0:
            # Detect a manually issued BEGIN too, before closing the worker connection.
            raise RuntimeError("historical_migration_outside_transaction_required")
        if (
            not isinstance(self.target, tuple)
            or len(self.target) != 2
            or any(not isinstance(value, str) or not value for value in self.target)
        ):
            raise RuntimeError("historical_migration_exact_target_required")

    def __enter__(self):
        self._guard()
        self.original_name = connection.settings_dict["NAME"]
        self.owned_name = self.prefix + uuid.uuid4().hex
        try:
            with connection._nodb_cursor() as cursor:
                cursor.execute(f"CREATE DATABASE {connection.ops.quote_name(self.owned_name)}")
            self.created = True
            connection.close()
            connection.settings_dict["NAME"] = self.owned_name
            MigrationExecutor(connection).migrate([self.target])
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        if self.original_name is None:
            return
        try:
            try:
                connection.close()
            finally:
                connection.settings_dict["NAME"] = self.original_name
        finally:
            if self.created:
                # Only this instance's unpredictable, owned test database is disposable.
                if not self.owned_name.startswith(self.prefix):
                    raise RuntimeError("historical_migration_owned_database_required")
                with connection._nodb_cursor() as cursor:
                    cursor.execute(f"DROP DATABASE {connection.ops.quote_name(self.owned_name)} WITH (FORCE)")
                self.created = False
        self.original_name = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def reset_sequences(self):
        if not self.created or connection.settings_dict["NAME"] != self.owned_name:
            raise RuntimeError("historical_migration_owned_database_required")
        historical_apps = MigrationExecutor(connection).loader.project_state([self.target]).apps
        with connection.cursor() as cursor:
            existing = set(connection.introspection.table_names(cursor))
            tables = {
                model._meta.db_table
                for model in historical_apps.get_models(include_auto_created=True)
                if model._meta.managed and not model._meta.proxy and model._meta.db_table in existing
            }
            sequences = [
                sequence
                for table in sorted(tables)
                for sequence in connection.introspection.get_sequences(cursor, table)
            ]
        # Current-model M2M tables may not exist yet; recorder metadata is not a historical model.
        sql = connection.ops.sequence_reset_by_name_sql(no_style(), sequences)
        with transaction.atomic(), connection.cursor() as cursor:
            for statement in sql:
                cursor.execute(statement)

    def assert_recorded_schema(self):
        if not self.created or connection.settings_dict["NAME"] != self.owned_name:
            raise RuntimeError("historical_migration_owned_database_required")
        loader = MigrationExecutor(connection).loader
        historical_apps = loader.project_state(nodes=list(loader.applied_migrations)).apps
        with connection.cursor() as cursor:
            for model in historical_apps.get_app_config(self.target[0]).get_models(include_auto_created=True):
                if not model._meta.managed or model._meta.proxy:
                    continue
                expected = {field.column for field in model._meta.local_concrete_fields}
                actual = {
                    column.name
                    for column in connection.introspection.get_table_description(cursor, model._meta.db_table)
                }
                if actual != expected:
                    raise AssertionError(f"historical_migration_schema_mismatch:{model._meta.db_table}")


class HistoricalMigrationTestCase(TransactionTestCase):
    """Keep existing migration assertions while leaving current-schema seeds intact.

    Each case owns its historical schema. Closing that database replaces the
    unrelated full-graph restore and flush; the ordinary worker database is
    never rewound or flushed by these tests. Normal pytest-django setup and
    the independent full migration build check remain unchanged.
    """

    historical_migration_target = None

    @classmethod
    def _fixture_setup(cls):
        target = cls.historical_migration_target
        if target and getattr(settings, "MIGRATION_MODULES", {}).get(target[0], object()) is None:
            raise SkipTest("MigrationExecutor testi --no-migrations rejimində işləmir.")
        if cls.available_apps is not None or cls.fixtures or cls.serialized_rollback:
            raise RuntimeError("historical_migration_extra_fixtures_not_supported")
        cls._historical_database = HistoricalDatabase(target)
        cls._historical_database.__enter__()
        try:
            if cls.reset_sequences:
                cls._historical_database.reset_sequences()
        except BaseException:
            cls._historical_database.close()
            raise

    def _fixture_teardown(self):
        database = getattr(self, "_historical_database", None)
        if database is not None:
            try:
                database.assert_recorded_schema()
            finally:
                database.close()
                type(self)._historical_database = None
