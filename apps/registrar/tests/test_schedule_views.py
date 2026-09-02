"""View-level tests for the timetable page (/cedvel/) — U4.

2026-09: slot əlavəsi/silinməsi ``schedule.manage`` açarına köçdü (bax
``apps/registrar/schedule_manage.py``). Adi müəllim artıq YALNIZ GÖRÜR —
gözləntilər buna uyğun yenilənib; icazə/əhatə matrisi ayrıca faylda
(``test_schedule_manage.py``).
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


class ScheduleViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sv_owner", "sv_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SV Univ",
                slug="sv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="sv-g1", unit_type=OrgUnitType.GROUP
            )
            # DİQQƏT: dövr CARİ olmalıdır — 2026-09-dan sonra slot əlavəsi
            # `schedule_manage.period_window_error` ilə bitmiş semestrdə
            # bloklanır, ona görə tarixlər sabit yox, bu günə görə qurulur.
            today = datetime.date.today()
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=120),
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("sv_teacher", "sv_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("sv_student", "sv_student@qku.edu.az", "pw")
            # `schedule.manage` daşıyan aktor — RİM (org-wide). Müəllim QƏSDƏN
            # bu açarı almır; slot yazan səth üçün ayrıca istifadəçi lazımdır.
            cls.manager = User.objects.create_user("sv_manager", "sv_manager@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student"), (cls.manager, "ikt_rehber")):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.student.profile.organization = cls.org
            cls.student.profile.save(update_fields=["organization"])
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
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
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 30),
                room="201",
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_requires_login(self):
        resp = Client().get(reverse("registrar:schedule"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_student_sees_group_schedule(self):
        resp = self._client(self.student).get(reverse("registrar:schedule"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["role"], "student")
        self.assertContains(resp, "CS101")
        self.assertContains(resp, "201")

    def test_teacher_sees_own_schedule_read_only(self):
        """Müəllim öz həftəsini GÖRÜR, amma idarəetmə düymələri YOXDUR."""
        resp = self._client(self.teacher).get(reverse("registrar:schedule"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["role"], "teacher")
        self.assertTrue(resp.context["teacher_offerings"])
        self.assertFalse(resp.context["schedule_can_manage"])
        self.assertNotContains(resp, "data-sgx-open-add")

    def test_teacher_cannot_add_slot(self):
        """`schedule.manage` olmadan açılışın MÜƏLLİMİ də slot yaza bilmir."""
        resp = self._client(self.teacher).post(
            reverse("registrar:schedule"),
            {
                "offering_id": str(self.offering.id),
                "weekday": "3",
                "start_time": "11:00",
                "end_time": "12:30",
                "room": "305",
                "week_type": "all",
            },
        )
        self.assertEqual(resp.status_code, 403)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(offering=self.offering, weekday=3).exists())

    def test_permission_holder_adds_slot(self):
        """`schedule.manage` daşıyan aktor (RİM) slot əlavə edə bilir."""
        resp = self._client(self.manager).post(
            reverse("registrar:schedule"),
            {
                "offering_id": str(self.offering.id),
                "weekday": "3",
                "start_time": "11:00",
                "end_time": "12:30",
                "room": "305",
                "week_type": "all",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(offering=self.offering, weekday=3, room="305").exists())

    def test_add_slot_conflict_shows_error(self):
        client = self._client(self.manager)
        # Overlaps the seeded Monday 09:00–10:30 slot (same offering/group/teacher).
        client.post(
            reverse("registrar:schedule"),
            {
                "offering_id": str(self.offering.id),
                "weekday": "1",
                "start_time": "10:00",
                "end_time": "11:00",
                "week_type": "all",
            },
        )
        with bypass_rls():
            # Only the original Monday slot remains (the conflicting one was rejected).
            self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering, weekday=1).count(), 1)
