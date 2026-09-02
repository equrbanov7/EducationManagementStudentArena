"""P2-1 reqressiya: nəzarət səthi hər autentifikasiya olunmuş üzvə açıq DEYİL.

2026-09-02 auditi (`docs/audits/2026-09-02/PHASE23_SECURITY.md`, hal 39):
`GET /exams/center/rooms/` TƏLƏBƏ hesabı ilə **200** qaytarırdı və tam
imtahan-nəzarət UI qabığını render edirdi.  Səbəb: `supervisor_org_or_403`
yalnız aktiv təşkilat konteksti olub-olmadığını soruşurdu, rol/təyinat
yoxlamırdı.  Data sızmırdı (queryset sonra boşalır), amma səth ümumiyyətlə
açılmamalı idi — və eyni helper `for_supervision=True` olan HƏR view-i qorumaq
üçün işlədilir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamRoom
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class SupervisionSurfaceGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sg_owner", "sg_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="SG University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.student = User.objects.create_user("sg_student", "sg_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.teacher = User.objects.create_user("sg_teacher", "sg_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.invigilator = User.objects.create_user("sg_inv", "sg_inv@test.az", PASSWORD)
        _assign_user_to_org(cls.invigilator, cls.org, ProfileRole.TEACHER, "teacher")
        cls.exam_center = User.objects.create_user("sg_center", "sg_center@test.az", PASSWORD)
        _assign_user_to_org(cls.exam_center, cls.org, ProfileRole.MEMBER, "exam_center")

        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal 38", capacity=30)
        cls.room.invigilators.add(cls.invigilator)

        cls.url = reverse("exams:exam_center_room_list")

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_student_cannot_open_the_supervision_landing_page(self):
        response = self._client_for(self.student).get(self.url)
        self.assertNotEqual(response.status_code, 200)
        self.assertIn(response.status_code, {302, 403})

    def test_unassigned_teacher_cannot_open_the_supervision_landing_page(self):
        response = self._client_for(self.teacher).get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_assigned_invigilator_can_open_it(self):
        response = self._client_for(self.invigilator).get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_exam_center_can_open_it(self):
        response = self._client_for(self.exam_center).get(self.url)
        self.assertEqual(response.status_code, 200)
