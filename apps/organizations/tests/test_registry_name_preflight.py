from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType


class RegistryNamePreflightTests(TransactionTestCase):
    def test_previous_collisions_are_identifiable_without_names_or_partial_changes(self):
        base = [("organizations", "0088_credit_recognition_rim_staff")]
        latest = [("organizations", "0089_unique_registry_unit_names")]
        owner = get_user_model().objects.create_user("preflight_owner")
        org = Organization.objects.create(name="Test", owner=owner, org_type=OrganizationType.UNIVERSITY)
        units = []

        def restore_schema():
            OrgUnit.objects.filter(pk__in=[unit.pk for unit in units]).delete()
            MigrationExecutor(connection).migrate(latest)

        self.addCleanup(restore_schema)
        MigrationExecutor(connection).migrate(base)
        for group in range(6):
            for member in range(6 if group == 0 else 2):
                spelling = "ƏLAVƏ" if member % 2 else "əlavə"
                units.append(
                    OrgUnit(
                        organization=org,
                        unit_type=OrgUnitType.FACULTY,
                        name=f"{group} {spelling}",
                        slug=f"{group}-{member}",
                    )
                )
        OrgUnit.objects.bulk_create(units)
        with self.assertRaises(RuntimeError) as failure:
            MigrationExecutor(connection).migrate(latest)
        detail = str(failure.exception)
        self.assertIn("6 active registry name collision group(s)", detail)
        self.assertEqual(detail.count(f"organization={org.pk}"), 5)
        first_group = sorted(str(unit.pk) for unit in units[:6])
        for pk in first_group[:5]:
            self.assertIn(pk, detail)
        self.assertNotIn(first_group[5], detail)
        for unit in units[-2:]:
            self.assertNotIn(str(unit.pk), detail)
        self.assertNotIn("əlavə", detail.lower())
        current = dict(OrgUnit.objects.filter(organization=org, is_active=True).values_list("pk", "name"))
        self.assertEqual(current, {unit.pk: unit.name for unit in units})
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('orgunit_active_registry_name_uniq') IS NULL")
            self.assertTrue(cursor.fetchone()[0])
