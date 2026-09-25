"""Az/ing hərflərinə və ayırıcılara dözümlü axtarış — accounts səthləri (sahib 2026-09-26).

Sahib: «qruplar və bütün search yerlərində az dili hərfləri ilə yazmağı nəzərə al,
en dilə olan nəticə gəlsin; qrup nömrəsi «234 K ing»dir, «234king» və s.
kombinasiyada da işləsin». Yoxlanılır (REAL endpoint/servis, DB ilə):

* tələbə reyestri (``student-registry`` fraqmenti, ``sr_q``) — «Aliyev»/«Eliyev» →
  «Əliyev», «Sahzad»/«Shahzad» → «Şahzad», «234king» → «234 K ing» qrupu;
* ⌘K qlobal axtarış — eyni tələbə sorğuları, fənn «Verilenler» → «Verilənlər», jurnalın qrupu «234king»;
* hədəf qrup seçicisi (``people_academic_groups``);
* view-as axtarışı (qrup nömrəsi kod rejimində) və RİM istifadəçi axtarışı.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.services.rim import search_users
from apps.accounts.services.rim.policy import RimActor
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services as registrar_services
from apps.registrar.models import AcademicStatus, Curriculum, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

from .test_student_services_sections import PASSWORD, StudentServicesBase
from .test_view_as import ViewAsTestBase, _add_member

User = get_user_model()

GROUP_NAME = "234 K ing"
GROUP_QUERIES = ("234king", "234k ing", "234-K-ing", "234 K ing")


class RegistryTolerantSearchTest(StudentServicesBase):
    """Tələbə reyestri — ad/soyad az/ing dözümlü, qrup adı kod rejimində."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.group_234 = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name=GROUP_NAME,
            slug="s2-234-k-ing",
        )
        cls.aliyev = cls._student("s2_aliyev", "Rauf", "Əliyev", cls.group_a)
        cls.shahzad = cls._student("s2_shahzad", "Şahzad", "Quliyev", cls.group_234)

    @classmethod
    def _student(cls, username, first, last, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD, first_name=first, last_name=last)
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2025,
            status=AcademicStatus.ENROLLED,
        )
        return user

    def _names(self, query):
        response = self._fragment("student_services", "student-registry", sr_q=query)
        self.assertEqual(response.status_code, 200)
        return [row["name"] for row in response.context["student_registry_section"]["rows"]]

    def test_latin_spelling_finds_schwa_surname(self):
        for query in ("Aliyev", "Eliyev", "aliyev rauf", "Əliyev"):
            with self.subTest(query=query):
                self.assertEqual(self._names(query), ["Rauf Əliyev"])

    def test_s_and_sh_find_sh_cedilla(self):
        for query in ("Sahzad", "Shahzad", "Şahzad"):
            with self.subTest(query=query):
                self.assertEqual(self._names(query), ["Şahzad Quliyev"])

    def test_compact_group_name(self):
        for query in GROUP_QUERIES:
            with self.subTest(query=query):
                self.assertEqual(self._names(query), ["Şahzad Quliyev"])
        self.assertEqual(self._names("Shahzad 234king"), ["Şahzad Quliyev"])
        self.assertEqual(self._names("Aliyev 234king"), [])

    def test_target_group_picker_matches_compact_group_name(self):
        client = self._client("student_services")
        for query in GROUP_QUERIES:
            with self.subTest(query=query):
                response = client.get(reverse("accounts:people_academic_groups"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["text"] for row in response.json()["results"]], [GROUP_NAME])


@override_settings(UNIVERSITY_MODE=True)
class GlobalSearchTolerantTest(TestCase):
    """⌘K — tələbələr (ad), fənlər, jurnallar (fənn + qrup adı)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("s2gs_owner", "s2gs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="S2 GS Univ",
                slug="s2-gs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name=GROUP_NAME, slug="s2gs-g1", unit_type=OrgUnitType.GROUP
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="KE-101", slug="s2gs-g2", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=cls.org, code="S2CS", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            cls.subject = Subject.objects.create(organization=cls.org, code="VB-101", name="Verilənlər bazası")
            cls.teacher = User.objects.create_user("s2gs_teacher", "s2gs_teacher@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("s2gs_dean", "s2gs_dean@qku.edu.az", "pw")
            cls.aliyev = User.objects.create_user(
                "s2gs_aliyev", "s2gs_aliyev@qku.edu.az", "pw", first_name="Rauf", last_name="Əliyev"
            )
            cls.shahzad = User.objects.create_user(
                "s2gs_shahzad", "s2gs_shahzad@qku.edu.az", "pw", first_name="Şahzad", last_name="Quliyev"
            )
            for user, role in (
                (cls.teacher, "teacher"),
                (cls.dean, "dean"),
                (cls.aliyev, "student"),
                (cls.shahzad, "student"),
            ):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            for user, group in ((cls.aliyev, cls.other_group), (cls.shahzad, cls.group)):
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2026,
                )
            offering = registrar_services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=period, group=cls.group
            )
            offering.instructor = cls.teacher
            offering.save(update_fields=["instructor"])

    def _groups(self, user, query):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:global_search"), {"q": query})
        self.assertEqual(response.status_code, 200)
        return {group["key"]: group for group in json.loads(response.content)["groups"]}

    def _titles(self, user, query, key):
        return [item["title"] for item in self._groups(user, query).get(key, {"items": []})["items"]]

    def test_students_found_by_latin_spelling(self):
        for query, expected in (
            ("Aliyev", "Rauf Əliyev"),
            ("Eliyev", "Rauf Əliyev"),
            ("Sahzad", "Şahzad Quliyev"),
            ("Shahzad", "Şahzad Quliyev"),
        ):
            with self.subTest(query=query):
                self.assertEqual(self._titles(self.dean, query, "students"), [expected])

    def test_students_found_by_compact_group_name(self):
        """Alt sətirdə görünən qrup adı da axtarılır: «234king» → «234 K ing» qrupunun tələbəsi."""
        for query in ("234king", "234k ing", "234-K-ing", "Shahzad 234k"):
            with self.subTest(query=query):
                self.assertEqual(self._titles(self.dean, query, "students"), ["Şahzad Quliyev"])
        self.assertEqual(self._titles(self.dean, "ke101", "students"), ["Rauf Əliyev"])

    def test_subject_and_journal_by_latin_spelling_and_compact_code(self):
        for query in ("Verilenler", "verilənlər baza", "VB101", "vb 101"):
            with self.subTest(query=query):
                self.assertEqual(self._titles(self.dean, query, "subjects"), ["VB-101 — Verilənlər bazası"])
        for query in ("Verilenler", "234king"):
            with self.subTest(query=query):
                self.assertEqual(self._titles(self.teacher, query, "journals"), ["VB-101 — Verilənlər bazası"])

    def test_navigation_is_letter_tolerant(self):
        titles = [item["title"] for item in self._groups(self.teacher, "cedvel")["nav"]["items"]]
        self.assertIn("Dərs cədvəli", titles)


class ViewAsAndRimTolerantSearchTest(ViewAsTestBase):
    """view-as siyahısı (qrup nömrəsi kod rejimində) + RİM istifadəçi axtarışı."""

    def setUp(self):
        super().setUp()
        self.target = User.objects.create_user(
            "s2va_shahzad", "s2va@example.com", PASSWORD, first_name="Şahzad", last_name="Əliyev"
        )
        self.target.profile.student_group_number = GROUP_NAME
        self.target.profile.save(update_fields=["student_group_number", "updated_at"])
        _add_member(self.target, self.org, self.student_role)

    def test_view_as_search_by_latin_name_and_compact_group(self):
        self._login(self.admin)
        for query in ("Shahzad Aliyev", "sahzad", "234king", "Eliyev 234k ing"):
            with self.subTest(query=query):
                response = self.client.get(reverse("accounts:view_as_search"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["username"] for row in response.json()["results"]], ["s2va_shahzad"])

    def test_rim_user_search_is_letter_tolerant(self):
        actor = RimActor(user=self.superadmin, organization=self.org, level=999, is_superadmin=True)
        for query in ("Shahzad", "Aliyev Sahzad", "Şahzad Əliyev"):
            with self.subTest(query=query):
                found = search_users(actor, query=query)
                self.assertEqual([user.pk for user in found["results"]], [self.target.pk])
