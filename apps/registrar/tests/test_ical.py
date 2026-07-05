"""U19 — dərs cədvəli iCal exportu testləri."""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import ical, schedule, services
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ScheduleIcsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ics_owner", "ics_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ICS Univ",
                slug="ics-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="ics-g1", unit_type=OrgUnitType.GROUP
            )
            # 2024-09-02 bazar ertəsidir → parity anchor sadə olsun.
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız 2024",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-02",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("ics_teacher", "ics_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("ics_student", "ics_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.offering = cls.student.enrollments.get().offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            # Çərşənbə (weekday=3), hər həftə + cümə (weekday=5), üst həftə.
            cls.slot_all = schedule.create_slot(
                offering=cls.offering,
                weekday=3,
                start_time=datetime.time(10, 0),
                end_time=datetime.time(11, 30),
                room="A-204",
                week_type=WeekType.ALL,
            )
            cls.slot_odd = schedule.create_slot(
                offering=cls.offering,
                weekday=5,
                start_time=datetime.time(14, 0),
                end_time=datetime.time(15, 30),
                week_type=WeekType.ODD,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── ical servis qatı ─────────────────────────────────────────────────────
    def test_ics_structure_and_events(self):
        with bypass_rls():
            slots = schedule.get_group_schedule(organization=self.org, group=self.group, period=self.period)
            payload = ical.build_schedule_ics(slots=slots, period=self.period, calendar_name="G1")
        self.assertTrue(payload.startswith("BEGIN:VCALENDAR"))
        self.assertIn("X-WR-CALNAME:G1", payload)
        self.assertEqual(payload.count("BEGIN:VEVENT"), 2)
        self.assertIn("SUMMARY:CS101 — Proqramlaşdırma", payload)
        self.assertIn("LOCATION:A-204", payload)
        self.assertIn("UNTIL=20250131T235959", payload)

    def test_weekly_slot_dtstart_and_rrule(self):
        with bypass_rls():
            payload = ical.build_schedule_ics(slots=[self.slot_all], period=self.period, calendar_name="G1")
        # İlk çərşənbə: 2024-09-04 (start 2024-09-02 bazar ertəsi).
        self.assertIn("DTSTART:20240904T100000", payload)
        self.assertIn("DTEND:20240904T113000", payload)
        self.assertIn("RRULE:FREQ=WEEKLY;INTERVAL=1;", payload)

    def test_odd_week_slot_anchored_and_biweekly(self):
        with bypass_rls():
            payload = ical.build_schedule_ics(slots=[self.slot_odd], period=self.period, calendar_name="G1")
        # Semestr 1-ci həftəsi üst (odd) → ilk cümə 2024-09-06-da qalır.
        self.assertIn("DTSTART:20240906T140000", payload)
        self.assertIn("INTERVAL=2", payload)

    def test_no_period_yields_empty_calendar(self):
        payload = ical.build_schedule_ics(slots=[], period=None, calendar_name="Boş")
        self.assertIn("BEGIN:VCALENDAR", payload)
        self.assertNotIn("BEGIN:VEVENT", payload)

    def test_text_escaping(self):
        self.assertEqual(ical._escape("a;b,c\nd"), "a\\;b\\,c\\nd")

    # ── endpoint ─────────────────────────────────────────────────────────────
    def test_student_downloads_group_ics(self):
        resp = self._client(self.student).get(reverse("registrar:schedule_ics"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/calendar", resp["Content-Type"])
        self.assertIn('filename="ders-cedveli.ics"', resp["Content-Disposition"])
        body = resp.content.decode()
        self.assertEqual(body.count("BEGIN:VEVENT"), 2)
        self.assertIn("X-WR-CALNAME:G1 — ICS Univ", body)

    def test_teacher_downloads_own_ics(self):
        resp = self._client(self.teacher).get(reverse("registrar:schedule_ics"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode().count("BEGIN:VEVENT"), 2)

    def test_anonymous_redirected(self):
        resp = Client().get(reverse("registrar:schedule_ics"))
        self.assertEqual(resp.status_code, 302)
