"""Sahib 2026-11-05: «sənəd yükləmə yerini pass keç» — RİM rəhbəri alt qrup yerləşdirməsində sənədsiz keçir.

Qeyd mətni rolu göstərir («RİM rəhbəri düzəlişi — sənədsiz …»); RİM əməkdaşı və müəllim üçün heç nə dəyişmir.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core import superadmin_waiver
from core.constants import OrganizationType

User = get_user_model()


class RimHeadDocumentWaiverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rhw_owner", "rhw_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="RHW Org", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.rim_head = User.objects.create_user(
            "rhw_head", "rhw_head@test.az", PASSWORD, first_name="Elvin", last_name="Q"
        )
        _assign_user_to_org(cls.rim_head, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.rim_staff = User.objects.create_user("rhw_staff", "rhw_staff@test.az", PASSWORD)
        _assign_user_to_org(cls.rim_staff, cls.org, ProfileRole.MEMBER, "rim_staff")
        cls.teacher = User.objects.create_user("rhw_teacher", "rhw_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

    def test_rim_head_waives_with_own_note(self):
        scope = superadmin_waiver.SUBGROUP
        self.assertTrue(superadmin_waiver.waives(self.rim_head, scope=scope))
        stamped = superadmin_waiver.stamp("Köhnə sistemdən alt qrup", self.rim_head, scope=scope)
        self.assertIn(superadmin_waiver.RIM_NOTE_PREFIX, stamped)
        self.assertTrue(superadmin_waiver.is_waiver_text(stamped))
        self.assertEqual(superadmin_waiver.stamp(stamped, self.rim_head, scope=scope), stamped)

    def test_rim_staff_and_teacher_do_not_waive(self):
        self.assertFalse(superadmin_waiver.waives(self.rim_staff, scope=superadmin_waiver.SUBGROUP))
        self.assertFalse(superadmin_waiver.waives(self.teacher, scope=superadmin_waiver.SUBGROUP))
        self.assertEqual(superadmin_waiver.stamp("x", self.teacher), "x")
        self.assertIsNone(superadmin_waiver.document_or_waiver(None, self.teacher))

    def test_rim_head_waiver_is_subgroup_only(self):
        """Jurnal düzəlişi / imtahan balı / məzun əmri kimi digər sənədli qapılar RİM rəhbəri üçün dəyişmir."""
        self.assertFalse(superadmin_waiver.waives(self.rim_head))
        self.assertEqual(superadmin_waiver.stamp("x", self.rim_head), "x")
        self.assertEqual(superadmin_waiver.fill_text("", self.rim_head, min_length=5), "")
        self.assertIsNone(superadmin_waiver.document_or_waiver(None, self.rim_head))
