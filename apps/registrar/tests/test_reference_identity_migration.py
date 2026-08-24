"""0045 forward/reverse lifecycle and history-loss STOP tests."""

import datetime
import uuid

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

from core.rls import bypass_rls


class ReferenceIdentityMigrationTest(TransactionTestCase):
    migrate_from = ("registrar", "0044_criterion_score_component_identity")
    migrate_to = ("registrar", "0045_reference_identity_and_group_transfer")

    def setUp(self):
        super().setUp()
        migration_modules = getattr(settings, "MIGRATION_MODULES", {})
        self._migrations_disabled = "registrar" in migration_modules and migration_modules["registrar"] is None
        if self._migrations_disabled:
            self.skipTest("MigrationExecutor testi --no-migrations rejimində işləmir.")
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate([self.migrate_from])
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence('auth_user', 'id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 1) FROM auth_user), 1))"
                )

    def _fixture_teardown(self):
        if getattr(self, "_migrations_disabled", False):
            return super()._fixture_teardown()
        recorder = MigrationRecorder(connection)
        applied = recorder.migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1])
        if not applied.exists():
            MigrationExecutor(connection).migrate([self.migrate_to])
        MigrationExecutor(connection).migrate(self.latest_targets)
        truncate_guard_tables = []
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT c.relname FROM pg_catalog.pg_trigger t "
                    "JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND NOT t.tgisinternal "
                    "AND (t.tgtype & 32) = 32"
                )
                truncate_guard_tables = [row[0] for row in cursor.fetchall()]
                for table in truncate_guard_tables:
                    cursor.execute(f"ALTER TABLE {connection.ops.quote_name(table)} DISABLE TRIGGER USER")
        try:
            return super()._fixture_teardown()
        finally:
            if truncate_guard_tables:
                with connection.cursor() as cursor:
                    for table in truncate_guard_tables:
                        cursor.execute(f"ALTER TABLE {connection.ops.quote_name(table)} ENABLE TRIGGER USER")

    def _apps(self, target):
        return MigrationExecutor(connection).loader.project_state([target]).apps

    def _history_fixture(self, apps):
        suffix = uuid.uuid4().hex[:10]
        User = apps.get_model("auth", "User")
        Organization = apps.get_model("organizations", "Organization")
        Role = apps.get_model("organizations", "Role")
        Membership = apps.get_model("organizations", "Membership")
        AcademicPeriod = apps.get_model("organizations", "AcademicPeriod")
        Subject = apps.get_model("registrar", "Subject")
        CourseOffering = apps.get_model("registrar", "CourseOffering")
        Enrollment = apps.get_model("registrar", "Enrollment")

        owner = User.objects.create(username=f"m45-owner-{suffix}", is_active=True)
        student = User.objects.create(username=f"m45-student-{suffix}", is_active=True)
        with bypass_rls():
            organization = Organization.objects.create(
                name=f"Migration 0045 {suffix}",
                slug=f"migration-0045-{suffix}",
                org_type="university",
                owner=owner,
                status="active",
                is_active=True,
            )
            role = Role.objects.create(
                organization=organization,
                name=f"m45-student-{suffix}",
                display_name="Migration student",
                scope_type="organization",
                permissions=[],
                is_active=True,
            )
            Membership.objects.create(
                organization=organization,
                user=student,
                role=role,
                is_active=True,
            )
            period = AcademicPeriod.objects.create(
                organization=organization,
                name=f"Period {suffix}",
                period_type="semester",
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
            )
            subject = Subject.objects.create(
                organization=organization,
                code=f"M45-{suffix}",
                name="Migration subject",
            )
            offering = CourseOffering.objects.create(
                organization=organization,
                subject=subject,
                period=period,
            )
            enrollment = Enrollment.objects.create(
                organization=organization,
                student=student,
                offering=offering,
            )
        return enrollment.pk

    def test_empty_forward_reverse_forward_round_trip(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1]).exists()
        )
        MigrationExecutor(connection).migrate([self.migrate_to])
        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1]).exists()
        )

    def test_existing_history_survives_forward_and_stops_reverse(self):
        old_apps = self._apps(self.migrate_from)
        enrollment_id = self._history_fixture(old_apps)
        MigrationExecutor(connection).migrate([self.migrate_to])
        new_apps = self._apps(self.migrate_to)
        self.assertTrue(new_apps.get_model("registrar", "Enrollment").objects.filter(pk=enrollment_id).exists())

        with self.assertRaisesRegex(RuntimeError, "registrar_0045_reverse_reference_history_present"):
            MigrationExecutor(connection).migrate([self.migrate_from])

        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1]).exists()
        )
        self.assertTrue(new_apps.get_model("registrar", "Enrollment").objects.filter(pk=enrollment_id).exists())
