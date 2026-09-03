"""R-1/R-4 — bitmiş `is_current` dövr cədvəli GÖRÜNMƏZ etməməlidir.

FAZA 27 auditinin tapıntısı: klonda `AcademicPeriod.is_current` 2025/2026 Yaz-dır
(bitmə tarixi 2026-06-30), yəni bu gün KEÇMİŞ semestrdir.  `my-schedule` YALNIZ
cari dövrü göstərirdi, `schedule_manage` isə bitmiş dövrə yazmağı rədd edirdi —
koordinatorun yarada bildiyi hər slot görünməz, görünən dövrə isə slot yazıla
bilmirdi.  Nəticədə cədvəl axını uçdan-uca işləmirdi.

Qayda (indi):

* `?period=<id>` verilibsə — həmin dövr (SPA boyunca saxlanılır);
* yoxsa cari dövr, ƏGƏR bu gün onun tarixləri arasındadırsa;
* yoxsa slotu OLAN ən yaxın gələcək dövr; o da yoxdursa slotu olan ƏN SON dövr;
* heç biri yoxdursa köhnə davranış (cari / ən son dövr) qalır.

`schedule_manage`-in «bitmiş dövr yalnız-oxudur» qaydası TOXUNULMUR.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, services
from apps.registrar.models import Curriculum, Program, ScheduleSlot, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class SchedulePeriodSelectionTest(TestCase):
    """Bitmiş cari dövr + slotu olan gələcək dövr."""

    @classmethod
    def setUpTestData(cls):
        today = datetime.date.today()
        cls.owner = User.objects.create_user("spx_owner", "spx_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SPX Univ",
                slug="spx-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="SPX-G1", slug="spx-g1", unit_type=OrgUnitType.GROUP
            )
            # BİTMİŞ dövr, amma `is_current=True` — auditdəki real vəziyyət.
            cls.ended = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=today - datetime.timedelta(days=210),
                end_date=today - datetime.timedelta(days=60),
                is_current=True,
            )
            # Slotu OLAN gələcək dövr.
            cls.upcoming = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today + datetime.timedelta(days=14),
                end_date=today + datetime.timedelta(days=150),
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="SPX101", name="Alqoritmlər")
            cls.teacher = User.objects.create_user("spx_teacher", "spx_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("spx_student", "spx_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.student.profile.organization = cls.org
            cls.student.profile.save(update_fields=["organization"])

            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.upcoming, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            program = Program.objects.create(organization=cls.org, code="SPX", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2024,
            )
            schedule.create_slot(
                offering=cls.offering,
                weekday=3,
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                room="SPX 101",
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── Göstərilən dövrün seçimi ───────────────────────────────────────────

    def test_student_sees_the_upcoming_period_when_the_current_one_has_ended(self):
        response = self._client(self.student).get(reverse("registrar:schedule"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.upcoming)
        self.assertContains(response, "SPX 101")

    def test_teacher_sees_the_same_period(self):
        response = self._client(self.teacher).get(reverse("registrar:schedule"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.upcoming)
        self.assertContains(response, "SPX 101")

    def test_explicit_period_query_wins_and_is_kept_in_the_nav_links(self):
        response = self._client(self.student).get(reverse("registrar:schedule"), {"period": str(self.ended.id)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.ended)
        # Həftə pillələri seçilmiş dövrü İTİRMİR.
        self.assertIn(f"period={self.ended.id}", response.context["schedule_nav_prefix"])

    def test_selector_lists_both_periods_and_marks_the_selected_one(self):
        response = self._client(self.student).get(reverse("registrar:schedule"))

        choices = response.context["schedule_period_choices"]
        self.assertEqual({str(row["id"]) for row in choices}, {str(self.ended.id), str(self.upcoming.id)})
        self.assertEqual(response.context["schedule_selected_period_id"], str(self.upcoming.id))
        self.assertContains(response, "data-sgx-period")

    def test_a_current_period_that_is_still_running_wins(self):
        """Cari dövr BİTMƏYİBSƏ davranış dəyişmir — köhnə səthin qorunması."""
        today = datetime.date.today()
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.ended.pk).update(
                start_date=today - datetime.timedelta(days=10),
                end_date=today + datetime.timedelta(days=100),
            )
        response = self._client(self.student).get(reverse("registrar:schedule"))

        self.assertEqual(str(response.context["period"].id), str(self.ended.id))

    def test_a_stale_old_period_never_beats_the_current_one(self):
        """Köhnə semestrdən qalma slot 4 il geri «zaman səyahəti» etməməlidir."""
        today = datetime.date.today()
        with bypass_rls():
            ancient = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2022/2023",
                start_date=today - datetime.timedelta(days=1400),
                end_date=today - datetime.timedelta(days=1250),
            )
            old_offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=ancient, group=self.group
            )
            old_offering.instructor = self.teacher
            old_offering.save(update_fields=["instructor"])
            schedule.create_slot(
                offering=old_offering,
                weekday=2,
                start_time=datetime.time(8, 30),
                end_time=datetime.time(10, 0),
                room="SPX KÖHNƏ",
            )
            # Gələcək dövrün slotunu götürürük ki, yeganə slotlu dövr KÖHNƏ olsun.
            ScheduleSlot.objects.filter(offering__period=self.upcoming).delete()

        response = self._client(self.student).get(reverse("registrar:schedule"))

        self.assertEqual(str(response.context["period"].id), str(self.ended.id))
        self.assertNotContains(response, "SPX KÖHNƏ")
