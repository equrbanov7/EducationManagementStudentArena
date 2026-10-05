"""Təhlükəsizlik auditi 2026-10-05 — ⌘K qlobal axtarışın tələbə qrupu struktur scope-ludur.

``_student_group`` bütün təşkilatın akademik qeydlərini axtarırdı: ``member.view`` +
``unit.view`` daşıyan UNIT-scope-lu aktor (dekan, koordinator) öz fakültəsindən
kənar tələbələri ad/username/e-poçt ilə tapırdı. E-poçt üzrə axtarış həm də
kontakt icazəsi (``people.view_contacts``) olmayan aktora e-poçt oracle-ı verirdi.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class GlobalSearchStudentScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("gss_owner", "gss_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GSS Univ",
                slug="gss-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            faculty_a = OrgUnit.objects.create(
                organization=cls.org, name="Fak A", slug="gss-fa", unit_type=OrgUnitType.FACULTY
            )
            faculty_b = OrgUnit.objects.create(
                organization=cls.org, name="Fak B", slug="gss-fb", unit_type=OrgUnitType.FACULTY
            )
            group_a = OrgUnit.objects.create(
                organization=cls.org, name="GA-1", slug="gss-ga", unit_type=OrgUnitType.GROUP, parent=faculty_a
            )
            group_b = OrgUnit.objects.create(
                organization=cls.org, name="GB-1", slug="gss-gb", unit_type=OrgUnitType.GROUP, parent=faculty_b
            )
            program = Program.objects.create(organization=cls.org, code="GSS", name="Proqram")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            cls.own_student = User.objects.create_user(
                "gss_own", "zzqownmail@qku.edu.az", "pw", first_name="Qorxmaz", last_name="Doğmaoğlu"
            )
            cls.foreign_student = User.objects.create_user(
                "gss_foreign", "gss_foreign@qku.edu.az", "pw", first_name="Yadigar", last_name="Uzaqbəyli"
            )
            for student, group in ((cls.own_student, group_a), (cls.foreign_student, group_b)):
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    scope_unit=group,
                    is_primary=True,
                    is_active=True,
                )
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2024,
                )
            role = Role.objects.create(
                organization=cls.org,
                name="gss_directory",
                display_name="Directory",
                level=60,
                scope_type=RoleScopeType.UNIT,
                permissions=["member.view", "unit.view"],
                is_active=True,
            )
            cls.officer = User.objects.create_user("gss_officer", "gss_officer@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.officer,
                organization=cls.org,
                role=role,
                scope_unit=faculty_a,
                is_primary=True,
                is_active=True,
            )

    def _search(self, q):
        client = Client()
        client.force_login(self.officer)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:global_search"), {"q": q})
        self.assertEqual(response.status_code, 200)
        groups = {g["key"]: g for g in json.loads(response.content)["groups"]}
        return [item["title"] for item in groups.get("students", {}).get("items", [])]

    def test_student_inside_scope_is_found(self):
        self.assertIn("Qorxmaz Doğmaoğlu", self._search("Doğmaoğlu"))

    def test_student_outside_scope_is_not_found(self):
        self.assertEqual(self._search("Uzaqbəyli"), [])

    def test_email_is_not_searchable_without_contact_permission(self):
        self.assertEqual(self._search("zzqownmail"), [])
