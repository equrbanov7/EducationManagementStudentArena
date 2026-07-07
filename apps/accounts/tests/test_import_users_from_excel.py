"""
Excel-dən istifadəçi toplu-import əmri (import_users_from_excel) testləri.
"""

import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()

_HEADER = ["username", "ad_soyad", "rol", "teskilat_slug", "vahid", "ilkin_parol", "qeyd"]


class ImportUsersFromExcelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("imp_owner", "imp_owner@t.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Imp Uni",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            slug="imp-uni",
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə X")

    def _make_xlsx(self, rows):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "İstifadəçilər"
        ws.append(_HEADER)
        for row in rows:
            ws.append(row)
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        wb.save(path)
        return path

    def test_imports_users_with_roles_and_first_login(self):
        path = self._make_xlsx(
            [
                ["imp_teacher", "Ali Vəli", "teacher", "imp-uni", "", "Parol123!", ""],
                ["imp_dean", "Nurlan Cəfər", "dean", "imp-uni", "Fakültə X", "", ""],
                ["imp_student", "Aygün Hüseyn", "student", "imp-uni", "", "", ""],
            ]
        )
        try:
            call_command("import_users_from_excel", "--file", path)
        finally:
            os.unlink(path)

        teacher = User.objects.get(username="imp_teacher")
        self.assertTrue(teacher.check_password("Parol123!"))
        self.assertTrue(teacher.profile.password_change_required)
        self.assertFalse(teacher.profile.email_verified)
        self.assertTrue(Membership.objects.filter(user=teacher, organization=self.org, role__name="teacher").exists())

        dean = User.objects.get(username="imp_dean")
        membership = Membership.objects.get(user=dean, role__name="dean")
        self.assertEqual(membership.scope_unit, self.faculty)

        self.assertTrue(User.objects.filter(username="imp_student").exists())

    def test_existing_username_is_skipped(self):
        User.objects.create_user("imp_existing", "e@t.az", "keepme")
        path = self._make_xlsx([["imp_existing", "X Y", "teacher", "imp-uni", "", "changed!", ""]])
        try:
            call_command("import_users_from_excel", "--file", path)
        finally:
            os.unlink(path)
        # Mövcud istifadəçi ÖTÜRÜLÜR — parolu dəyişmir.
        self.assertTrue(User.objects.get(username="imp_existing").check_password("keepme"))

    def test_unknown_role_is_error_not_created(self):
        path = self._make_xlsx([["imp_bad", "X Y", "not_a_role", "imp-uni", "", "", ""]])
        try:
            call_command("import_users_from_excel", "--file", path)
        finally:
            os.unlink(path)
        self.assertFalse(User.objects.filter(username="imp_bad").exists())

    def test_dry_run_creates_nothing(self):
        path = self._make_xlsx([["imp_dry", "X Y", "teacher", "imp-uni", "", "", ""]])
        try:
            call_command("import_users_from_excel", "--file", path, "--dry-run")
        finally:
            os.unlink(path)
        self.assertFalse(User.objects.filter(username="imp_dry").exists())
