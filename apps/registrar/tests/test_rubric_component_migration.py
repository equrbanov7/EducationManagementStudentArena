"""0044 component-identity migration lifecycle and fail-closed STOP tests."""

import datetime
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

import pytest

from core.rls import bypass_rls

# Miqrasiya round-trip (migrate → sıfıra → geri) testləri xdist-də 4 worker-in
# paralel miqrasiyası altında 300 s qlobal limiti keçə bilir (Develop run
# 33778014237 flake-i); modul üçün limit ayrıca qaldırılır.
pytestmark = pytest.mark.timeout(1200)


class CriterionComponentMigrationTest(TransactionTestCase):
    migrate_from = ("registrar", "0043_correction_reversal_ledger")
    migrate_to = ("registrar", "0044_criterion_score_component_identity")

    def setUp(self):
        super().setUp()
        migration_modules = getattr(settings, "MIGRATION_MODULES", {})
        self._migrations_disabled = "registrar" in migration_modules and migration_modules["registrar"] is None
        if self._migrations_disabled:
            self.skipTest("MigrationExecutor testi --no-migrations rejimində işləmir.")
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate([self.migrate_to])
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence('auth_user', 'id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 1) FROM auth_user), 1))"
                )

    def _fixture_teardown(self):
        if getattr(self, "_migrations_disabled", False):
            return super()._fixture_teardown()
        executor = MigrationExecutor(connection)
        applied = MigrationRecorder(connection).migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1])
        if not applied.exists():
            old_apps = executor.loader.project_state([self.migrate_from]).apps
            with bypass_rls():
                old_apps.get_model("registrar", "CriterionScore").objects.all().delete()
            executor.migrate([self.migrate_to])

        new_apps = MigrationExecutor(connection).loader.project_state([self.migrate_to]).apps
        with bypass_rls(), transaction.atomic():
            new_apps.get_model("registrar", "CriterionScore").objects.all().delete()
            new_apps.get_model("registrar", "ComponentScore").objects.all().delete()
        MigrationExecutor(connection).migrate(self.latest_targets)
        truncate_guard_tables = []
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT c.relname
                      FROM pg_catalog.pg_trigger t
                      JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'public' AND NOT t.tgisinternal
                       AND (t.tgtype & 32) = 32
                    """)
                truncate_guard_tables = [row[0] for row in cursor.fetchall()]
                for table in truncate_guard_tables:
                    cursor.execute(f"ALTER TABLE {connection.ops.quote_name(table)} DISABLE TRIGGER USER")
        try:
            super()._fixture_teardown()
        finally:
            if truncate_guard_tables:
                with connection.cursor() as cursor:
                    for table in truncate_guard_tables:
                        cursor.execute(f"ALTER TABLE {connection.ops.quote_name(table)} ENABLE TRIGGER USER")

    def _apps(self, target):
        return MigrationExecutor(connection).loader.project_state([target]).apps

    def _fixture(self, apps, *, component_count=1):
        suffix = uuid.uuid4().hex[:10]
        User = apps.get_model("auth", "User")
        Organization = apps.get_model("organizations", "Organization")
        AcademicPeriod = apps.get_model("organizations", "AcademicPeriod")
        Subject = apps.get_model("registrar", "Subject")
        CourseOffering = apps.get_model("registrar", "CourseOffering")
        Enrollment = apps.get_model("registrar", "Enrollment")
        Role = apps.get_model("organizations", "Role")
        Membership = apps.get_model("organizations", "Membership")
        Rubric = apps.get_model("registrar", "Rubric")
        RubricCriterion = apps.get_model("registrar", "RubricCriterion")
        AssessmentComponent = apps.get_model("registrar", "AssessmentComponent")

        owner = User.objects.create(username=f"m44-owner-{suffix}")
        student = User.objects.create(username=f"m44-student-{suffix}")
        with bypass_rls():
            organization = Organization.objects.create(
                name=f"Migration 0044 {suffix}",
                slug=f"migration-0044-{suffix}",
                org_type="university",
                owner=owner,
                status="active",
                is_active=True,
            )
            student_role = Role.objects.create(
                organization=organization,
                name=f"migration-student-{suffix}",
                display_name="Migration student",
                scope_type="organization",
                permissions=[],
                is_active=True,
            )
            Membership.objects.create(
                organization=organization,
                user=student,
                role=student_role,
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
                code=f"M44-{suffix}",
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
            rubric = Rubric.objects.create(organization=organization, name=f"Rubric {suffix}")
            criterion = RubricCriterion.objects.create(
                organization=organization,
                rubric=rubric,
                name="Criterion",
                max_points=4,
            )
            components = [
                AssessmentComponent.objects.create(
                    organization=organization,
                    offering=offering,
                    rubric=rubric,
                    name=f"Component {index}",
                    max_score=10,
                )
                for index in range(component_count)
            ]
        return {
            "organization": organization,
            "enrollment": enrollment,
            "criterion": criterion,
            "components": components,
        }

    def _migrate_forward_fails(self, code):
        with self.assertRaisesRegex(RuntimeError, code):
            MigrationExecutor(connection).migrate([self.migrate_to])
        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app=self.migrate_to[0], name=self.migrate_to[1]).exists()
        )

    def test_valid_evidence_survives_reverse_forward_round_trip(self):
        apps = self._apps(self.migrate_to)
        fixture = self._fixture(apps)
        component = fixture["components"][0]
        ComponentScore = apps.get_model("registrar", "ComponentScore")
        CriterionScore = apps.get_model("registrar", "CriterionScore")
        with bypass_rls():
            ComponentScore.objects.create(
                organization=fixture["organization"],
                component=component,
                enrollment=fixture["enrollment"],
                score=2,
            )
            score = CriterionScore.objects.create(
                organization=fixture["organization"],
                component=component,
                criterion=fixture["criterion"],
                enrollment=fixture["enrollment"],
                points=2,
            )

        MigrationExecutor(connection).migrate([self.migrate_from])
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(cursor, "registrar_criterionscore")
            }
        self.assertNotIn("component_id", columns)

        MigrationExecutor(connection).migrate([self.migrate_to])
        migrated = self._apps(self.migrate_to).get_model("registrar", "CriterionScore").objects.get(pk=score.pk)
        self.assertEqual(migrated.component_id, component.pk)

    def test_forward_stops_when_component_resolution_is_ambiguous(self):
        apps = self._apps(self.migrate_to)
        fixture = self._fixture(apps, component_count=2)
        MigrationExecutor(connection).migrate([self.migrate_from])
        old_apps = self._apps(self.migrate_from)
        with bypass_rls():
            old_apps.get_model("registrar", "CriterionScore").objects.create(
                organization_id=fixture["organization"].pk,
                criterion_id=fixture["criterion"].pk,
                enrollment_id=fixture["enrollment"].pk,
                points=2,
            )
        self._migrate_forward_fails("registrar_0044_component_resolution_failed")

    def test_forward_stops_for_invalid_points(self):
        apps = self._apps(self.migrate_to)
        fixture = self._fixture(apps)
        MigrationExecutor(connection).migrate([self.migrate_from])
        old_apps = self._apps(self.migrate_from)
        with bypass_rls():
            old_apps.get_model("registrar", "CriterionScore").objects.create(
                organization_id=fixture["organization"].pk,
                criterion_id=fixture["criterion"].pk,
                enrollment_id=fixture["enrollment"].pk,
                points=5,
            )
        self._migrate_forward_fails("registrar_0044_points_invalid")

    def test_forward_stops_for_mismatched_component_total(self):
        apps = self._apps(self.migrate_to)
        fixture = self._fixture(apps)
        component = fixture["components"][0]
        MigrationExecutor(connection).migrate([self.migrate_from])
        old_apps = self._apps(self.migrate_from)
        with bypass_rls():
            old_apps.get_model("registrar", "ComponentScore").objects.create(
                organization_id=fixture["organization"].pk,
                component_id=component.pk,
                enrollment_id=fixture["enrollment"].pk,
                score=1,
            )
            old_apps.get_model("registrar", "CriterionScore").objects.create(
                organization_id=fixture["organization"].pk,
                criterion_id=fixture["criterion"].pk,
                enrollment_id=fixture["enrollment"].pk,
                points=2,
            )
        self._migrate_forward_fails("registrar_0044_component_total_mismatch")

    def test_reverse_stops_for_duplicate_cross_component_evidence(self):
        apps = self._apps(self.migrate_to)
        fixture = self._fixture(apps, component_count=2)
        ComponentScore = apps.get_model("registrar", "ComponentScore")
        CriterionScore = apps.get_model("registrar", "CriterionScore")
        with bypass_rls():
            for index, component in enumerate(fixture["components"], start=1):
                ComponentScore.objects.create(
                    organization=fixture["organization"],
                    component=component,
                    enrollment=fixture["enrollment"],
                    score=index,
                )
                CriterionScore.objects.create(
                    organization=fixture["organization"],
                    component=component,
                    criterion=fixture["criterion"],
                    enrollment=fixture["enrollment"],
                    points=index,
                )
        with self.assertRaisesRegex(RuntimeError, "registrar_0044_reverse_duplicate_component_evidence"):
            MigrationExecutor(connection).migrate([self.migrate_from])
