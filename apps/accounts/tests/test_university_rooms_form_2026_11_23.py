"""«Universitet otaqları» (əvvəl «İmtahan zalları») — sahib 2026-11-23.

* Otaq dialoqunda «Bina» sərbəst mətn deyil, seçimdir: korpus xəritəsi (``settings["campuses"]``) + reyestrdəki binalar.
* Eyni binada eyni adlı ikinci otaq yaradılmır (böyük/kiçik hərf, artıq boşluq fərq etmir); başqa binada eyni ad olar.
* Köhnə reyestrdə artıq olan cütün başqa sahəsini redaktə etmək bloklanmır.
* Sol menyuda bölmənin adı «Universitet otaqları».
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.forms.final_center import ExamRoomForm
from apps.exams.models import ExamRoom
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class UniversityRoomsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("uro_owner", "uro_owner@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="URO University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
            settings={"campuses": [{"building": "Korpus A", "units": []}]},
        )
        cls.room = ExamRoom.objects.create(organization=cls.org, name="101", code="A-101", building="Korpus B")
        cls.superadmin = User.objects.create_superuser("uro_admin", "uro_admin@test.az", "StrongPass123!")

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superadmin)

    def _create(self, **overrides):
        data = {
            "action": "create_room",
            "organization_id": str(self.org.pk),
            "room_id": "",
            "name": "101",
            "code": "NEW-1",
            "building": "Korpus B",
            "floor": "",
            "capacity": "0",
            "computer_count": "0",
            "notes": "",
            "is_active": "1",
            "next": reverse("accounts:profile") + "?section=superadmin-exam-rooms",
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:superadmin_exam_rooms"), data, **AJAX)

    def test_same_name_in_same_building_is_rejected(self):
        response = self._create(name="  101 ")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json()["errors"])
        self.assertEqual(ExamRoom.objects.filter(organization=self.org, name="101").count(), 1)

    def test_same_name_differs_only_by_case(self):
        ExamRoom.objects.create(organization=self.org, name="Zal A", code="ZA", building="Korpus B")
        response = self._create(name="zal a", code="ZA2")
        self.assertEqual(response.status_code, 400)

    def test_same_name_in_other_building_is_allowed(self):
        response = self._create(building="Korpus A")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(ExamRoom.objects.filter(organization=self.org, code="NEW-1", building="Korpus A").exists())

    def test_editing_existing_duplicate_pair_keeps_working(self):
        twin = ExamRoom.objects.create(organization=self.org, name="101", code="A-101B", building="Korpus B")
        form = ExamRoomForm(
            {
                "name": "101",
                "code": "A-101B",
                "building": "Korpus B",
                "floor": "2",
                "capacity": "30",
                "computer_count": "0",
                "notes": "",
                "is_active": "1",
            },
            instance=twin,
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_renaming_into_existing_name_is_rejected(self):
        other = ExamRoom.objects.create(organization=self.org, name="102", code="A-102", building="Korpus B")
        form = ExamRoomForm(
            {
                "name": "101",
                "code": "A-102",
                "building": "Korpus B",
                "floor": "",
                "capacity": "0",
                "computer_count": "0",
                "notes": "",
                "is_active": "1",
            },
            instance=other,
            organization=self.org,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_section_renders_building_select_and_new_menu_label(self):
        response = self.client.get(
            reverse("accounts:profile"), {"section": "superadmin-exam-rooms", "room_org": str(self.org.pk)}
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<select class="ems-select bootstrap-single-select__native" id="sar-room-building"', html)
        self.assertIn('<option value="Korpus A">Korpus A</option>', html)
        self.assertIn('<option value="Korpus B">Korpus B</option>', html)
        self.assertNotIn('<input class="ems-input" type="text" id="sar-room-building"', html)
        self.assertIn("Universitet otaqları", html)
