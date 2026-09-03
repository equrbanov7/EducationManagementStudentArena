"""P2-2 reqressiya: rol/icazə matrisi org-genişliyində sızmır.

2026-09-02 auditi (hal 27): FAKÜLTƏYƏ scope-lanmış dekan
`GET /organizations/<slug>/roles/` səhifəsini **200** ilə açırdı və bütün
təşkilatın rol kataloqunu + icazə matrisini görürdü.  Səbəb: qapı
`_can_manage_organization`-a bağlı idi, o da `level >= 80` üçün implicit
`org_admin` alias-ını qəbul edir.  POST heç nə dəyişmirdi (27c PASS), yəni bu
AÇIQLAMA idi, eskalasiya deyil — amma dekana aid olmayan struktur məlumatıdır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"


class RoleMatrixScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rm_owner", "rm_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="RM University",
            slug="rm-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.url = reverse("organizations:roles", kwargs={"slug": cls.org.slug})

        cls.dean = User.objects.create_user("rm_dean", "rm_dean@test.az", PASSWORD)
        Membership.objects.create(
            user=cls.dean, organization=cls.org, role=cls.org.roles.get(name="dean"), is_active=True
        )
        # Rektor: idarəetmə səviyyəsi (>=80) VƏ wildcard icazə → `role.view` var.
        cls.rector = User.objects.create_user("rm_rector", "rm_rector@test.az", PASSWORD)
        Membership.objects.create(
            user=cls.rector, organization=cls.org, role=cls.org.roles.get(name="rector"), is_active=True
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_faculty_scoped_dean_cannot_read_the_org_wide_role_matrix(self):
        response = self._client_for(self.dean).get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_role_view_holder_still_reads_it(self):
        response = self._client_for(self.rector).get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_owner_still_reads_it(self):
        response = self._client_for(self.owner).get(self.url)
        self.assertEqual(response.status_code, 200)
