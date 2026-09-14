"""İKT Rəhbəri üçün «Registrar (kataloq)» bölməsi bağlı olmamalıdır.

Şikayət (2026-07-29): sidebar-da «Registrar (kataloq)» linki görünürdü, açanda
404 gəlirdi. Səbəb: sidebar `role_capabilities.can_manage_registrar` ilə
qərar verirdi, view isə ayrıca `_REGISTRAR_ADMIN_ROLES` siyahısına baxırdı və
`ikt_rehber` orada yox idi — iki fərqli predikat.

2026-09-10: köhnə müstəqil konsol (`registrar:console`) silindi — səth kabinet
bölməsidir (`?section=registrar-catalog`) + JSON son nöqtəsi
(`accounts:registrar_catalog_action`). Testin MƏNASI dəyişmir: sidebar-ın
predikatı ilə səthin qapısı EYNİ olmalıdır — İKT Rəhbəri girir, adi müəllim yox.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class IktRehberRegistrarConsoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("irc_owner", "irc_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="IRC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.ikt = User.objects.create_user("irc_ikt", "irc_ikt@test.az", PASSWORD)
        _assign_user_to_org(cls.ikt, cls.org, ProfileRole.ORG_ADMIN, "ikt_rehber")

        cls.teacher = User.objects.create_user("irc_teacher", "irc_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _section(self, user):
        response = self._client_for(user).get(f"{reverse('accounts:profile')}?section=registrar-catalog")
        self.assertEqual(response.status_code, 200)
        return response.context["registrar_catalog_section"]

    def _action_status(self, user):
        """Naməlum `action` — icazəsi olan 400, olmayan 403 alır (fail-closed)."""
        return (
            self._client_for(user)
            .post(reverse("accounts:registrar_catalog_action"), data={"action": "", "tab": "programs"})
            .status_code
        )

    def test_ikt_rehber_opens_registrar_catalog_section(self):
        self.assertTrue(self._section(self.ikt)["has_access"], msg="İKT Rəhbəri hələ də bağlı qapı görür")
        self.assertEqual(self._action_status(self.ikt), 400)

    def test_plain_teacher_still_gets_no_access(self):
        """Reqressiya qoruması: kataloq hamıya açılmayıb."""
        self.assertFalse(self._section(self.teacher)["has_access"])
        self.assertEqual(self._action_status(self.teacher), 403)
