"""Tests for the academic calendar (U11): window states + calendar view."""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class CalendarTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cal_owner", "cal_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CAL Univ",
                slug="cal-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.student = User.objects.create_user("cal_student", "cal_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            today = timezone.localdate()
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=90),
                registration_start=today - datetime.timedelta(days=5),
                registration_end=today + datetime.timedelta(days=5),
                exam_session_start=today + datetime.timedelta(days=80),
                exam_session_end=today + datetime.timedelta(days=95),
                is_current=True,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── Window-state model helpers ───────────────────────────────────────────
    def test_window_states(self):
        self.assertEqual(self.period.registration_state, "open")
        self.assertEqual(self.period.exam_session_state, "upcoming")

    def test_closed_and_unset_windows(self):
        today = timezone.localdate()
        with bypass_rls():
            past = AcademicPeriod.objects.create(
                organization=self.org,
                name="Keçmiş semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2020/2021",
                start_date=today - datetime.timedelta(days=700),
                end_date=today - datetime.timedelta(days=550),
                registration_start=today - datetime.timedelta(days=720),
                registration_end=today - datetime.timedelta(days=700),
            )
        self.assertEqual(past.registration_state, "closed")
        self.assertIsNone(past.exam_session_state)  # not configured

    # ── View ─────────────────────────────────────────────────────────────────
    def test_calendar_lists_periods_with_badges(self):
        resp = self._client(self.student).get(reverse("registrar:calendar"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cari semestr")
        self.assertContains(resp, "acal-state--open")  # registration open
        self.assertContains(resp, "acal-state--upcoming")  # exam session upcoming

    def test_anonymous_redirected(self):
        resp = Client().get(reverse("registrar:calendar"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)


class RegistrationWindowEnforcementTest(TestCase):
    """U14 — seçmə-fənn qərarı yalnız qeydiyyat pəncərəsi açıq olanda (staff override var)."""

    @classmethod
    def setUpTestData(cls):
        from apps.registrar.models import Curriculum, CurriculumSubject, Program, Subject
        from core.constants import OrgUnitType

        cls.owner = User.objects.create_user("rw_owner", "rw_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RW Univ",
                slug="rw-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            from apps.organizations.models import OrgUnit

            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="rw-g1", unit_type=OrgUnitType.GROUP
            )
            today = timezone.localdate()
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="RW semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=10),
                end_date=today + datetime.timedelta(days=100),
                registration_start=today - datetime.timedelta(days=30),
                registration_end=today - datetime.timedelta(days=5),  # BAĞLANIB
            )
            cls.program = Program.objects.create(organization=cls.org, code="RW", name="RW proqram")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
            cls.subject = Subject.objects.create(organization=cls.org, code="RW101", name="Seçmə fənn")
            CurriculumSubject.objects.create(
                organization=cls.org,
                curriculum=cls.curriculum,
                subject=cls.subject,
                semester_number=1,
                is_elective=True,
                elective_group="Blok A",
            )

    def _choose(self, **kwargs):
        from apps.registrar import services

        return services.choose_group_elective(
            organization=self.org,
            group=self.group,
            curriculum=self.curriculum,
            period=self.period,
            elective_group="Blok A",
            subject=self.subject,
            **kwargs,
        )

    def test_closed_window_blocks_choice(self):
        from apps.registrar.services import RegistrationWindowClosed

        with bypass_rls():
            with self.assertRaises(RegistrationWindowClosed):
                self._choose()

    def test_staff_override_bypasses_window(self):
        with bypass_rls():
            choice, _count = self._choose(enforce_window=False)
            self.assertEqual(choice.chosen_subject_id, self.subject.id)

    def test_open_window_allows_choice(self):
        today = timezone.localdate()
        with bypass_rls():
            self.period.registration_end = today + datetime.timedelta(days=5)
            self.period.save(update_fields=["registration_end"])
            choice, _count = self._choose()
            self.assertEqual(choice.chosen_subject_id, self.subject.id)

    def test_unconfigured_window_allows_choice(self):
        with bypass_rls():
            self.period.registration_start = None
            self.period.registration_end = None
            self.period.save(update_fields=["registration_start", "registration_end"])
            choice, _count = self._choose()
            self.assertEqual(choice.chosen_subject_id, self.subject.id)
