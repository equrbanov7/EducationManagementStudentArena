"""Sahib 2026-10-11: «Kurs işi» RİM tənzimləməsi ilə idarə olunur, hələlik SÖNDÜRÜLÜ.

2026/2027 açılışında jurnalda tab, stepper addımı, birbaşa POST, sənədli düzəliş və tələbənin öz jurnalındakı
kurs işi bloku yoxdur. Köhnə (2025/2026) semestr dəyişmir; ``ACADEMIC_COURSEWORK_ENABLED=True`` (və ya RİM
açarı) ilə 2026/2027-də də hamısı geri qayıdır — kod, model və data toxunulmur.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import item_corrections, services
from apps.registrar.models import CourseWork, Enrollment, Subject
from core import academic_rules
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

TAB = 'data-jtab="kurs-isi"'
STEP = 'data-jd-step="4"'
PANEL = 'id="jd-panel-kurs-isi"'


class CourseworkHiddenJournalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cwh_owner", "cwh_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CWH Univ",
                slug="cwh-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CWH101", name="Kurs işsiz fənn")
            cls.teacher = User.objects.create_user("cwh_teacher", "cwh_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("cwh_student", "cwh_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            cls.new_offering, cls.new_enrollment = cls._offering("2026/2027", datetime.date(2026, 9, 15), True)
            cls.old_offering, cls.old_enrollment = cls._offering("2025/2026", datetime.date(2025, 9, 15), False)

    @classmethod
    def _offering(cls, year, start, current):
        group = OrgUnit.objects.create(
            organization=cls.org, name=f"CWH-{year[:4]}", slug=f"cwh-g-{year[:4]}", unit_type=OrgUnitType.GROUP
        )
        period = AcademicPeriod.objects.create(
            organization=cls.org,
            name=f"Payız {year}",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=year,
            start_date=start,
            end_date=start + datetime.timedelta(days=130),
            is_current=current,
        )
        offering = services.get_or_create_offering(
            organization=cls.org, subject=cls.subject, period=period, group=group
        )
        offering.instructor = cls.teacher
        offering.lesson_hours = 60
        offering.save(update_fields=["instructor", "lesson_hours"])
        enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=offering)
        return offering, enrollment

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _detail(self, offering, query=""):
        url = reverse("registrar:journal_detail", args=[offering.id]) + query
        response = self._client(self.teacher).get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def _save(self, offering, enrollment):
        url = reverse("registrar:journal_coursework_save", args=[offering.id])
        return self._client(self.teacher).post(
            url, {"cw_enrollment": str(enrollment.id), "cw_topic": "Mövzu", "cw_score": "80"}
        )

    def test_default_is_off_and_old_periods_keep_coursework(self):
        self.assertFalse(academic_rules.coursework_enabled())
        self.assertFalse(academic_rules.coursework_active_for_offering(self.new_offering))
        self.assertTrue(academic_rules.coursework_active_for_offering(self.old_offering))
        self.assertFalse(academic_rules.snapshot()["coursework"])

    def test_new_rule_journal_has_no_coursework_tab_or_step(self):
        response = self._detail(self.new_offering)
        self.assertFalse(response.context["coursework_active"])
        self.assertNotContains(response, TAB)
        self.assertNotContains(response, STEP)
        self.assertContains(response, 'data-jtab="yekun"')
        # Görünən nömrələr sürüşür: Qrup 1 · Davamiyyət 2 · Yeni dərs 3 · Yekun 4 (sərbəst iş də söndürülü).
        self.assertRegex(response.content.decode(), r'data-jd-step="6"[^>]*>\s*<span class="jd2-step-no[^"]*">4<')

    def test_new_rule_tab_url_falls_back_to_grid(self):
        response = self._detail(self.new_offering, "?jt=kurs-isi")
        self.assertEqual(response.context["active_tab"], "grid")
        self.assertNotContains(response, PANEL)

    def test_new_rule_direct_post_is_refused_and_writes_nothing(self):
        self.assertEqual(self._save(self.new_offering, self.new_enrollment).status_code, 404)
        with bypass_rls():
            self.assertFalse(CourseWork.objects.filter(enrollment=self.new_enrollment).exists())

    def test_new_rule_documented_correction_is_refused(self):
        with self.assertRaises(ValidationError):
            item_corrections.ensure_coursework_active(self.new_offering)
        item_corrections.ensure_coursework_active(self.old_offering)  # köhnə semestr — xəta yoxdur

    def test_old_period_journal_keeps_coursework(self):
        response = self._detail(self.old_offering, "?jt=kurs-isi")
        self.assertTrue(response.context["coursework_active"])
        self.assertContains(response, TAB)
        self.assertContains(response, STEP)
        self.assertContains(response, PANEL)
        self.assertEqual(self._save(self.old_offering, self.old_enrollment).status_code, 302)

    @override_settings(ACADEMIC_COURSEWORK_ENABLED=True)
    def test_switching_it_back_on_restores_everything(self):
        response = self._detail(self.new_offering, "?jt=kurs-isi")
        self.assertTrue(response.context["coursework_active"])
        self.assertContains(response, TAB)
        self.assertContains(response, STEP)
        self.assertContains(response, PANEL)
        self.assertEqual(self._save(self.new_offering, self.new_enrollment).status_code, 302)
        with bypass_rls():
            self.assertTrue(CourseWork.objects.filter(enrollment=self.new_enrollment).exists())
