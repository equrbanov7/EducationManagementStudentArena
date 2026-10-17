"""QA-1 P2 (2026-10-17): profil tamamlama qapısı tələbənin imtahan SİYAHISINI dayandırırdı.

``/exams/`` və ``/exams/available/`` qapıdan keçirdi, amma kabinetin ``?section=…`` bölməsinə yönləndirirdi və
o, qapılı idi — tələbə imtahan günü siyahıya çata bilmirdi. İndi yalnız ``assigned-exams`` bölməsi (səhifə +
AJAX fraqmenti) açıqdır; kabinetin qalan bölmələri, müəllimin ``my-exams`` bölməsi və POST qapılı qalır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


@override_settings(PROFILE_COMPLETION_ENABLED=True)
class ExamListThroughProfileGateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("fxd_owner", "fxd_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="FXD Univ", slug="fxd-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="student",
            defaults={
                "display_name": "student",
                "level": 10,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_active": True,
            },
        )
        cls.student = User.objects.create_user("fxd_student", "fxd_student@gmail.com", "pw")
        profile = cls.student.profile
        profile.fin = None  # vacib sahə boşdur → qapı açıqdır
        profile.phone = "050 111 22 33"
        profile.organization = cls.org
        profile.save(update_fields=["fin", "phone", "organization", "updated_at"])
        Membership.objects.create(user=cls.student, organization=cls.org, role=role, is_primary=True, is_active=True)

    def setUp(self):
        rs.invalidate()
        self.client = Client()
        self.client.force_login(self.student)
        self.gate = reverse("accounts:complete_profile")
        self.profile = reverse("accounts:profile")

    def _gated(self, response) -> bool:
        if response.status_code == 403:
            return bool(response.json().get("profile_completion_required"))
        return response.headers.get("Location", "").startswith(self.gate)

    def test_general_cabinet_is_still_gated(self):
        self.assertTrue(self._gated(self.client.get(self.profile)))
        self.assertTrue(self._gated(self.client.get(self.profile, {"section": "my-results"})))
        self.assertTrue(self._gated(self.client.get(self.profile, {"section": "my-exams"})))

    def test_exam_list_section_is_reachable(self):
        response = self.client.get(self.profile, {"section": "assigned-exams"})
        self.assertFalse(self._gated(response))
        self.assertEqual(response.status_code, 200)

    def test_exam_section_fragment_is_reachable_but_others_are_not(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        fragment = reverse("accounts:profile_section_fragment", kwargs={"section": "assigned-exams"})
        self.assertFalse(self._gated(self.client.get(fragment, headers=headers)))
        other = reverse("accounts:profile_section_fragment", kwargs={"section": "my-results"})
        self.assertTrue(self._gated(self.client.get(other, headers=headers)))

    def test_exam_root_urls_end_on_the_student_exam_list(self):
        for path in ("/exams/", "/exams/available/", "/exams/assigned/"):
            response = self.client.get(path, follow=True)
            final = response.redirect_chain[-1][0] if response.redirect_chain else path
            self.assertNotIn(self.gate, final, path)
            self.assertEqual(response.status_code, 200, path)
        response = self.client.get("/exams/")
        self.assertEqual(response.headers["Location"], f"{self.profile}?section=assigned-exams")

    def test_post_with_exam_section_is_still_gated(self):
        response = self.client.post(f"{self.profile}?section=assigned-exams", {})
        self.assertTrue(self._gated(response))
