"""«Yekun qiymət» tabının audit sütunları (UNEC müqayisəsi P3, 2026-09-25):
Auditoriya saatı (plan / keçirilib) · Buraxılan saat · Qayıb % — kanonik məxrəclə, əlavə sorğusuz."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_extras, services
from apps.registrar.models import Enrollment, LessonKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class FinalBreakdownAuditColumnsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("fa_owner", "fa_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="FA Univ",
                slug="fa-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="fa-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=40),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="FA101", name="Statistika")
            cls.teacher = User.objects.create_user("fa_teacher", "fa_teacher@qku.edu.az", "pw")
            cls.students = [User.objects.create_user(f"fa_s{i}", f"fa_s{i}@qku.edu.az", "pw") for i in range(3)]
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            for student in cls.students:
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 20
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollments = [
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering)
                for student in cls.students
            ]
            past = [
                gradebook.create_lesson(
                    allow_past=True,
                    offering=cls.offering,
                    date=today - datetime.timedelta(days=days),
                    kind=LessonKind.LECTURE,
                )
                for days in (21, 14, 7)
            ]
            # Gələcək tarixli dərs PLANLAŞDIRILIB, amma «keçirilib» sayılmır.
            gradebook.create_lesson(offering=cls.offering, date=today + datetime.timedelta(days=7))
            # 1-ci tələbə iki dərsdə qayıb → 4 saat.
            gradebook.save_marks(
                enforce_day=False,
                offering=cls.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": cls.enrollments[0].id, "status": "absent"}
                    for lesson in past[:2]
                ],
                by_user=cls.teacher,
            )

    def _breakdown(self):
        with bypass_rls():
            return journal_extras.get_final_breakdown(self.offering)

    def _row(self, breakdown, enrollment):
        return next(row for row in breakdown["rows"] if row["enrollment"].id == enrollment.id)

    def test_columns_use_the_canonical_denominator(self):
        breakdown = self._breakdown()
        self.assertEqual(breakdown["lesson_hours"], Decimal("20"))
        self.assertEqual(breakdown["held_hours"], 6)
        absent = self._row(breakdown, self.enrollments[0])
        self.assertEqual(absent["absence_hours"], 4)
        self.assertEqual(absent["absence_pct"], Decimal("20.0"))
        clean = self._row(breakdown, self.enrollments[1])
        self.assertEqual(clean["absence_pct"], Decimal("0.0"))

    def test_fallback_denominator_is_the_lesson_sum(self):
        with bypass_rls():
            self.offering.lesson_hours = 0
            self.offering.save(update_fields=["lesson_hours"])
        breakdown = self._breakdown()
        # `exam_eligibility.lesson_hours_for` — plan yoxdursa BÜTÜN dərslərin saatı (4 × 2).
        self.assertEqual(breakdown["lesson_hours"], Decimal("8"))
        self.assertEqual(self._row(breakdown, self.enrollments[0])["absence_pct"], Decimal("50.0"))

    def test_no_denominator_shows_no_percent(self):
        with bypass_rls():
            self.offering.lesson_hours = 0
            self.offering.save(update_fields=["lesson_hours"])
            self.offering.lessons.all().delete()
        breakdown = self._breakdown()
        self.assertTrue(all(row["absence_pct"] is None for row in breakdown["rows"]))

    def test_columns_add_no_queries_per_row(self):
        def count():
            with bypass_rls(), CaptureQueriesContext(connection) as captured:
                journal_extras.get_final_breakdown(self.offering)
            return len(captured)

        count()
        three = count()
        with bypass_rls():
            for i in range(3, 6):
                student = User.objects.create_user(f"fa_s{i}", f"fa_s{i}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=self.org,
                    role=self.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
        self.assertEqual(count(), three)

    def test_yekun_tab_renders_the_columns(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(reverse("registrar:journal_detail", args=[self.offering.id]), {"jt": "yekun"})
        self.assertEqual(resp.status_code, 200)
        for header in ("AUDİTORİYA SAATI", "BURAXILAN SAAT", "QAYIB %"):
            self.assertContains(resp, header)
        self.assertContains(resp, "jd2-fb-pct")
        self.assertContains(resp, "6 / 20")
