"""Jurnal siyahısının «MÜƏLLİM» seçicisi — siyahı ilə EYNİ əhatə + az/ing dözümlü axtarış (2026-10-29).

Regressiya: seçici əvvəl ``accounts:journal_teacher_search``-ə (``student.records_view`` əhatəsi)
gedirdi. Proqram koordinatoru / kurator (``journal.roster``) və ``journal.view`` daşıyıcısı
siyahıda jurnalları görür, seçicidə isə heç bir müəllim tapmırdı.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Subject
from apps.registrar.page_contexts import journal_list_context
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalListTeacherSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("jlt_owner", "jlt_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JLT Univ",
                slug="jlt-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = OrgUnit.objects.create
            cls.fac_a = unit(organization=cls.org, name="Fak A", slug="jlt-fa", unit_type=OrgUnitType.FACULTY)
            cls.fac_b = unit(organization=cls.org, name="Fak B", slug="jlt-fb", unit_type=OrgUnitType.FACULTY)
            spec_a = unit(
                organization=cls.org, name="İxt A", slug="jlt-sa", unit_type=OrgUnitType.SPECIALTY, parent=cls.fac_a
            )
            spec_b = unit(
                organization=cls.org, name="İxt B", slug="jlt-sb", unit_type=OrgUnitType.SPECIALTY, parent=cls.fac_b
            )
            group_a = unit(organization=cls.org, name="A1", slug="jlt-ga", unit_type=OrgUnitType.GROUP, parent=spec_a)
            group_b = unit(organization=cls.org, name="B1", slug="jlt-gb", unit_type=OrgUnitType.GROUP, parent=spec_b)
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - timedelta(days=10),
                end_date=today + timedelta(days=100),
                is_current=True,
            )

            def member(user, role, scope_unit=None):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=scope_unit,
                    is_primary=True,
                    is_active=True,
                )

            cls.teachers = {}
            for index, (username, first, last, group) in enumerate(
                (
                    ("jlt_firuze", "Firuzə", "Əliyeva", group_a),
                    ("jlt_aide", "Aidə", "İsmayılova", group_a),
                    ("jlt_shahla", "Şəhla", "Çələbi", group_a),
                    ("jlt_other", "Ülvi", "Öztürk", group_b),  # başqa fakültə
                )
            ):
                teacher = User.objects.create_user(
                    username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last
                )
                member(teacher, "teacher")
                subject = Subject.objects.create(organization=cls.org, code=f"JLT{index}", name=f"Fənn {index}")
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=period, group=group
                )
                offering.instructor = teacher
                offering.save(update_fields=["instructor"])
                cls.teachers[username] = teacher
            cls.corrector = User.objects.create_user("jlt_rim", "jlt_rim@qku.edu.az", "pw")
            member(cls.corrector, "ikt_rehber")
            cls.coordinator = User.objects.create_user("jlt_coord", "jlt_coord@qku.edu.az", "pw")
            member(cls.coordinator, "program_coordinator", cls.fac_a)

    def _search(self, user, q=""):
        self.client.force_login(user)
        response = self.client.get(reverse("registrar:journal_list_teachers"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _names(self, user, q=""):
        return [row["text"] for row in self._search(user, q)["results"]]

    def test_partial_case_and_azerbaijani_letters_find_the_teacher(self):
        cases = {
            "fir": "Firuzə Əliyeva",
            "FİR": "Firuzə Əliyeva",
            "aida": "Aidə İsmayılova",
            "AİDƏ": "Aidə İsmayılova",
            "isma": "Aidə İsmayılova",
            "İSMA": "Aidə İsmayılova",
            "şəh": "Şəhla Çələbi",
            "seh": "Şəhla Çələbi",
            "cele": "Şəhla Çələbi",
            "ulvi": "Ülvi Öztürk",
            "Firuzə Əli": "Firuzə Əliyeva",
            "əliyeva firuzə": "Firuzə Əliyeva",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(self._names(self.corrector, query), [expected])

    def test_roster_coordinator_gets_the_teachers_of_their_own_list(self):
        # Köhnə endpoint (`student.records_view`) koordinatora BOŞ qaytarırdı — seçici «işləmirdi».
        self.client.force_login(self.coordinator)
        legacy = self.client.get(reverse("accounts:journal_teacher_search"), {"q": "fir"}).json()
        self.assertEqual(legacy["results"], [])
        self.assertEqual(self._names(self.coordinator, "fir"), ["Firuzə Əliyeva"])
        # Əhatə siyahı ilə eynidir: başqa fakültənin müəllimi çıxmır.
        self.assertEqual(self._names(self.coordinator, "ulvi"), [])
        request = RequestFactory().get("/jurnal/")
        request.user, request.organization, request.session = self.coordinator, self.org, {}
        with bypass_rls():
            listed = {row["value"] for row in journal_list_context(self.coordinator, request)["journal_teachers"]}
        returned = {row["id"] for row in self._search(self.coordinator)["results"]}
        self.assertEqual(returned, listed)

    def test_selected_teacher_filters_the_list(self):
        teacher_id = self._search(self.corrector, "aida")["results"][0]["id"]
        response = self.client.get(reverse("registrar:journal_list"), {"teacher": teacher_id})
        self.assertEqual(response.status_code, 200)
        offerings = response.context["offerings"]
        self.assertTrue(offerings)
        self.assertEqual({o.instructor_id for o in offerings}, {self.teachers["jlt_aide"].pk})

    def test_page_points_the_picker_at_the_list_scoped_endpoint(self):
        self.client.force_login(self.corrector)
        html = self.client.get(reverse("registrar:journal_list")).content.decode()
        self.assertIn(f'data-teacher-url="{reverse("registrar:journal_list_teachers")}"', html)

    def test_pagination_and_plain_teacher(self):
        first = self._search(self.corrector)
        self.assertEqual(len(first["results"]), 4)
        self.assertFalse(first["has_more"])
        self.client.force_login(self.corrector)
        page = self.client.get(reverse("registrar:journal_list_teachers"), {"limit": 2, "offset": 0}).json()
        self.assertEqual(len(page["results"]), 2)
        self.assertTrue(page["has_more"])
        # Adi müəllimin geniş görünüşü yoxdur → seçici də boşdur (başqa müəllimləri sızdırmır).
        self.assertEqual(self._search(self.teachers["jlt_firuze"], "aida")["results"], [])

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse("registrar:journal_list_teachers"), {"q": "fir"})
        self.assertEqual(response.status_code, 302)
