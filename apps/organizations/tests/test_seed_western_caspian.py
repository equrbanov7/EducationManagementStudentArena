"""Tests for the seed_western_caspian management command."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class SeedWesternCaspianCommandTest(TransactionTestCase):
    """The demo tenant must be created with the full role + academic hierarchy."""

    PASSWORD = "DemoPass123!"

    def _seed(self, **kwargs):
        out = StringIO()
        call_command("seed_western_caspian", "--password", self.PASSWORD, stdout=out, verbosity=1, **kwargs)
        return out

    def test_seeds_org_hierarchy_and_all_roles(self):
        self._seed()

        with bypass_rls():
            org = Organization.objects.get(slug="qerbi-kaspi-universiteti")
            # Academic hierarchy: Faculty → Chair → Specialty → Group(s) (AZ + EN sectors)
            faculty = OrgUnit.objects.get(organization=org, unit_type=OrgUnitType.FACULTY)
            chair = OrgUnit.objects.get(organization=org, unit_type=OrgUnitType.CHAIR)
            specialty = OrgUnit.objects.get(organization=org, unit_type=OrgUnitType.SPECIALTY)
            groups = list(OrgUnit.objects.filter(organization=org, unit_type=OrgUnitType.GROUP))
            self.assertEqual(chair.parent_id, faculty.id)
            self.assertEqual(specialty.parent_id, chair.id)
            self.assertEqual(len(groups), 2, "expected an AZ-sector and an EN-sector group")
            for group in groups:
                self.assertEqual(group.parent_id, specialty.id)

            # Every seeded role user has a membership; lab_assistant + scoped roles present.
            role_names = set(Membership.objects.filter(organization=org).values_list("role__name", flat=True))
            for expected in {
                "rector",
                "vice_rector",
                "exam_center",
                "hr",
                "dean",
                "chair_head",
                "teacher",
                "assistant",
                "lab_assistant",
                "tutor",
                "program_coordinator",
                "lead_student",
                "student",
            }:
                self.assertIn(expected, role_names, f"missing role membership: {expected}")

            # Dean is scoped to the faculty; every student is scoped to a sector group.
            dean_membership = Membership.objects.get(organization=org, role__name="dean")
            self.assertEqual(dean_membership.scope_unit_id, faculty.id)
            group_ids = {g.id for g in groups}
            for student in Membership.objects.filter(organization=org, role__name="student"):
                self.assertIn(student.scope_unit_id, group_ids)

        rector = User.objects.get(username="wcu_rector")
        self.assertTrue(rector.check_password(self.PASSWORD))
        self.assertEqual(org.owner_id, rector.id)

    def test_command_is_idempotent(self):
        self._seed()
        self._seed()  # second run must not raise or duplicate

        with bypass_rls():
            org = Organization.objects.get(slug="qerbi-kaspi-universiteti")
            # 5 units: faculty, chair, specialty, + AZ-sector and EN-sector groups.
            self.assertEqual(OrgUnit.objects.filter(organization=org).count(), 5)
            # 17 seeded role users → one primary membership each.
            self.assertEqual(Membership.objects.filter(organization=org).count(), 17)

    def test_without_superadmin_flag_no_superuser_created(self):
        self._seed()
        self.assertFalse(User.objects.filter(username="wcu_superadmin").exists())

    def test_with_superadmin_flag_creates_superuser(self):
        self._seed(with_superadmin=True)
        admin = User.objects.get(username="wcu_superadmin")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.check_password(self.PASSWORD))
