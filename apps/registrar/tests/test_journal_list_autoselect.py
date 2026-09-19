"""Jurnal siyahısında tədris ili + yarım il CARİ semestrə avto-seçilir — hər
görünüşdə (sahib qərarı 2026-09-20). Əvvəllər korrektor/admin (geniş) görünüşü
default «Hamısı» açırdı. «Hamısı» açıq seçim kimi hələ də mümkündür
(``?year=&season=``) və yalnız o halda «Sıfırla» görünür.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Subject
from apps.registrar.page_contexts import journal_list_context
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalListAutoSelectTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ja_owner", "ja_owner@qku.edu.az", "pw")
        today = date.today()
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JA Univ",
                slug="ja-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="ja-g1", unit_type=OrgUnitType.GROUP
            )
            # Cari dövr (bu günü əhatə edir) + keçmiş dövr.
            cls.current = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - timedelta(days=10),
                end_date=today + timedelta(days=100),
                is_current=True,
            )
            cls.past = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Keçmiş",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date=date(2024, 9, 15),
                end_date=date(2025, 1, 31),
                is_current=False,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="S1", name="Fənn")
            cls.admin = User.objects.create_user("ja_admin", "ja_admin@qku.edu.az", "pw", is_superuser=True)
            cls.teacher = User.objects.create_user("ja_teacher", "ja_teacher@qku.edu.az", "pw")
            for user, role in ((cls.admin, "ikt_rehber"), (cls.teacher, "teacher")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            for period in (cls.current, cls.past):
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=cls.subject, period=period, group=cls.group
                )
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])

    def _ctx(self, user, query=""):
        request = RequestFactory().get("/jurnal/" + query)
        request.user = user
        request.organization = self.org
        request.session = {}
        with bypass_rls():
            return journal_list_context(user, request)

    def test_broad_view_defaults_to_current_semester(self):
        ctx = self._ctx(self.admin)
        self.assertTrue(ctx["journal_is_broad"])
        self.assertEqual(ctx["journal_selected_year"], "2026/2027")
        self.assertTrue(ctx["journal_selected_season"])
        self.assertEqual([o.period_id for o in ctx["offerings"]], [self.current.pk])
        # Avto-seçim filtr sayılmır → «Sıfırla» yoxdur.
        self.assertFalse(ctx["journal_has_filters"])

    def test_teacher_view_still_defaults_to_current_semester(self):
        ctx = self._ctx(self.teacher)
        self.assertFalse(ctx["journal_is_broad"])
        self.assertEqual(ctx["journal_selected_year"], "2026/2027")

    def test_explicit_all_shows_every_period_and_reset(self):
        ctx = self._ctx(self.admin, "?year=&season=")
        self.assertEqual(ctx["journal_selected_year"], "")
        self.assertEqual(ctx["journal_selected_season"], "")
        self.assertEqual({o.period_id for o in ctx["offerings"]}, {self.current.pk, self.past.pk})
        self.assertTrue(ctx["journal_has_filters"])

    def test_explicit_past_year(self):
        ctx = self._ctx(self.admin, "?year=2024/2025")
        self.assertEqual(ctx["journal_selected_year"], "2024/2025")
        self.assertEqual([o.period_id for o in ctx["offerings"]], [self.past.pk])
