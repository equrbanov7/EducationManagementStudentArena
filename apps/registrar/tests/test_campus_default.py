"""Dərs modalında korpus defoltu — qrupun ixtisasına görə (sahib qərarı 2026-09-20).

Xəritə ``Organization.settings["campuses"]``-dədir (data, kod deyil). Yoxlanılır:
* ixtisas adı ata zəncirində fakültədən ƏVVƏL tapılır (eyni fakültənin iki
  ixtisası fərqli korpusda ola bilir);
* ad normallaşdırılır (böyük/kiçik hərf, «İ/ı», artıq boşluq);
* uyğunluq yoxdursa boş — modal əvvəlki kimi korpussuz açılır;
* jurnal səhifəsi ``data-default-building``-i modala yazır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import ExamRoom
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import campus, services
from apps.registrar.models import Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

CAMPUSES = [
    {"building": "Korpus A", "address": "17A", "units": ["İqtisadiyyat və biznes məktəbi", "Ekologiya"]},
    {"building": "Korpus B", "address": "21", "units": ["Yüksək texnologiyalar və innovativ mühəndislik"]},
]


class CampusDefaultTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cd_owner", "cd_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CD Univ",
                slug="cd-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
                settings={"campuses": CAMPUSES},
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org,
                name="Yüksək texnologiyalar və innovativ mühəndislik",
                slug="cd-yt",
                unit_type=OrgUnitType.FACULTY,
            )
            # Eyni fakültənin iki ixtisası: biri xəritədə (A), digəri yox (fakültəyə düşür → B).
            cls.eco = OrgUnit.objects.create(
                organization=cls.org,
                name="EKOLOGİYA",
                slug="cd-eco",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.faculty,
            )
            cls.ce = OrgUnit.objects.create(
                organization=cls.org,
                name="Kompüter Mühəndisliyi",
                slug="cd-ce",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.faculty,
            )
            cls.eco_group = OrgUnit.objects.create(
                organization=cls.org, name="234 EKO az", slug="cd-g-eco", unit_type=OrgUnitType.GROUP, parent=cls.eco
            )
            cls.ce_group = OrgUnit.objects.create(
                organization=cls.org, name="234 K az", slug="cd-g-ce", unit_type=OrgUnitType.GROUP, parent=cls.ce
            )
            cls.orphan_group = OrgUnit.objects.create(
                organization=cls.org, name="Sərbəst", slug="cd-g-x", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("cd_teacher", "cd_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.ce_group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            ExamRoom.objects.create(organization=cls.org, name="11", code="B11", building="Korpus B", capacity=20)
            ExamRoom.objects.create(organization=cls.org, name="201", code="A201", building="Korpus A", capacity=40)
            ExamRoom.objects.create(
                organization=cls.org, name="12", code="myedu-room-217", building="Korpus C", capacity=0
            )

    def test_specialty_wins_over_faculty(self):
        with bypass_rls():
            self.assertEqual(campus.default_building_for_group(self.org, self.eco_group), "Korpus A")
            self.assertEqual(campus.default_building_for_group(self.org, self.ce_group), "Korpus B")

    def test_no_match_is_empty(self):
        with bypass_rls():
            self.assertEqual(campus.default_building_for_group(self.org, self.orphan_group), "")
            self.assertEqual(campus.default_building_for_group(self.org, None), "")

    def test_missing_or_malformed_map_is_fail_open(self):
        with bypass_rls():
            self.org.settings = {}
            self.assertEqual(campus.default_building_for_group(self.org, self.ce_group), "")
            self.org.settings = {"campuses": ["x", {"units": ["Ekologiya"]}, {"building": "", "units": []}]}
            self.assertEqual(campus.campus_entries(self.org), [])

    def test_name_normalisation(self):
        self.assertEqual(campus.normalize_unit_name("  İnformasiya   Təhlükəsizliyi "), "informasiya tehlukesizliyi")
        self.assertEqual(campus.normalize_unit_name("EKOLOGİYA"), campus.normalize_unit_name("Ekologiya"))
        self.assertEqual(campus.normalize_unit_name("Tarix (Tədris Ingilis Dilində)"), "tarix (tedris ingilis dilinde)")

    def test_legacy_room_code_is_hidden_from_label(self):
        from apps.registrar import lesson_rooms

        with bypass_rls():
            names = {r["name"] for r in lesson_rooms.lesson_room_choices(self.offering)}
        self.assertIn("12", names)
        self.assertIn("11 (B11)", names)
        self.assertFalse(any("myedu-room" in n for n in names))

    def test_journal_page_passes_default_to_modal(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        html = resp.content.decode()
        self.assertIn('data-default-building="Korpus B"', html)
        self.assertIn("«Korpus B» seçilib", html)
