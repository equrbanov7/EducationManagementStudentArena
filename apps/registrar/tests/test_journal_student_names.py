"""Jurnalda tələbə adı «Soyad Ad Ata adı» + xana «kimindir» işarələri (sahib 2026-10-10).

Sütun başlığı həmişə «№ · SOYAD AD ATA ADI» idi, sətir isə ``get_full_name`` («Ad Soyad»,
ata adı yox) göstərirdi — ad-soyadı eyni iki tələbə ayırd edilmirdi.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.journal_names import journal_student_name
from apps.registrar.models import Enrollment, LessonKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalStudentNameHelperTest(TestCase):
    def _user(self, username, first="", last="", patronymic=""):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(patronymic=patronymic)
        return User.objects.select_related("profile").get(pk=user.pk)

    def test_surname_name_patronymic_order(self):
        user = self._user("jsn_a", "Əli", "Vəliyev", "Həsən")
        self.assertEqual(journal_student_name(user), "Vəliyev Əli Həsən")

    def test_missing_patronymic_is_skipped(self):
        user = self._user("jsn_b", "Əli", "Vəliyev")
        self.assertEqual(journal_student_name(user), "Vəliyev Əli")

    def test_missing_profile_does_not_raise(self):
        user = self._user("jsn_c", "Əli", "Vəliyev", "Həsən")
        UserProfile.objects.filter(user=user).delete()
        fresh = User.objects.select_related("profile").get(pk=user.pk)
        self.assertEqual(journal_student_name(fresh), "Vəliyev Əli")

    def test_falls_back_to_username(self):
        user = self._user("jsn_d")
        self.assertEqual(journal_student_name(user), "jsn_d")
        self.assertEqual(journal_student_name(None), "")


class JournalGridStudentNameTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jsn_owner", "jsn_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JSN Univ",
                slug="jsn-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(organization=cls.org, name="G1", slug="jsn-g1", unit_type=OrgUnitType.GROUP)
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=cls.org, code="CS102", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("jsn_teacher", "jsn_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=subject, period=period, group=group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            gradebook.create_lesson(
                allow_past=True, offering=cls.offering, date=timezone.localdate(), kind=LessonKind.SEMINAR
            )
        cls.add_student("jsn_s1", "Əli", "Vəliyev", "Həsən")

    @classmethod
    def add_student(cls, username, first, last, patronymic):
        with bypass_rls():
            student = User.objects.create_user(
                username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last
            )
            UserProfile.objects.filter(user=student).update(patronymic=patronymic)
            Membership.objects.create(
                user=student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering)

    def _get(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client.get(reverse("registrar:journal_detail", args=[self.offering.id]))

    def test_row_shows_surname_name_patronymic(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Vəliyev Əli Həsən")
        self.assertNotContains(resp, "Əli Vəliyev")

    def test_grid_carries_hover_hint_markers(self):
        resp = self._get()
        self.assertContains(resp, "data-jd-hint>")
        self.assertContains(resp, "data-jd-hint-name>Vəliyev Əli Həsən<")
        self.assertContains(resp, f'data-jd-hint-col="{timezone.localdate():%d.%m.%Y} · ')
        self.assertContains(resp, "registrar/js/journal_cell_hint.js")
        self.assertContains(resp, "registrar/css/journal_cell_hint.css")

    def test_patronymic_adds_no_per_row_query(self):
        def profile_selects():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self._get().status_code, 200)
            return sum(1 for q in ctx.captured_queries if 'FROM "accounts_userprofile"' in q["sql"])

        before = profile_selects()
        for index in range(3):
            self.add_student(f"jsn_extra{index}", "Ad", f"Soyad{index}", "Ata")
        self.assertEqual(profile_selects(), before)
