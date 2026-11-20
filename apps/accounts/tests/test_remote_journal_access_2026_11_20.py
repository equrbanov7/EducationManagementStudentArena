"""«Kənardan jurnal girişi» — kabinetdən verilən şəbəkə istisnası (sahib 2026-11-20).

Sahib: «Bu profilə access ver ki, kənardan mən kimi daxil ola bilsin … sistem tənzimləmələri yerində olsun, ordan
mən bunları əlavə edib çıxara bilim». Testlər: yalnız RİM rəhbəri / superadmin görür və yazır (digərlərinə 403 və
bölmə yoxdur); icazə → kənar zonadan jurnal açılır, geri alınma → yenə bağlıdır; mühit siyahısı əvvəlki kimi işləyir;
hər əməl audit jurnalına düşür; admin hesabda 2FA qaydası qalır.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.journal_remote_access import journal_remote_access_allowed
from apps.accounts.models import RemoteJournalAccess
from apps.accounts.network_zone import NetworkZoneMiddleware
from apps.accounts.services import remote_journal_access as service
from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.syllabus.tests.factories import make_org
from core.rls import bypass_rls

User = get_user_model()
SECTION = "remote-journal-access"


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("rja-univ")
            cls.head = User.objects.create_user("rja_head", "rja_head@qku.edu.az", "pw")
            cls.chair = User.objects.create_user(
                "rja_chair", "rja_chair@qku.edu.az", "pw", first_name="Kamil", last_name="Səmədli"
            )
            cls.teacher = User.objects.create_user("rja_teacher", "rja_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("rja_student", "rja_student@qku.edu.az", "pw")
            for user, role_name in (
                (cls.head, "ikt_rehber"),
                (cls.chair, "chair_head"),
                (cls.teacher, "teacher"),
                (cls.student, "student"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def post_action(self, user, payload):
        return self.client_for(user).post(
            reverse("accounts:remote_journal_access_action"), payload, content_type="application/json"
        )


@override_settings(RATELIMIT_ENABLE=False, JOURNAL_REMOTE_USER_IDS=())
class CabinetGateTest(_Base):
    def _sections(self, user):
        response = self.client_for(user).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    def test_only_rim_head_sees_the_section(self):
        self.assertIn(SECTION, self._sections(self.head))
        for user in (self.chair, self.teacher, self.student):
            self.assertNotIn(SECTION, self._sections(user), user.username)

    def test_others_get_403_on_lookup_and_action(self):
        for user in (self.chair, self.teacher, self.student):
            lookup = self.client_for(user).get(reverse("accounts:remote_journal_access_candidates"), {"q": "rja"})
            self.assertEqual(lookup.status_code, 403, user.username)
            self.assertEqual(lookup.json()["results"], [])
            action = self.post_action(user, {"action": "grant", "user": self.chair.pk})
            self.assertEqual(action.status_code, 403, user.username)
        self.assertFalse(RemoteJournalAccess.objects.exists())

    def test_candidates_list_staff_but_not_students(self):
        response = self.client_for(self.head).get(reverse("accounts:remote_journal_access_candidates"), {"q": "rja"})
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(str(self.chair.pk), ids)
        self.assertIn(str(self.teacher.pk), ids)
        self.assertNotIn(str(self.student.pk), ids)
        # Dözümlü ad axtarışı: «semedli» → «Səmədli».
        tolerant = self.client_for(self.head).get(
            reverse("accounts:remote_journal_access_candidates"), {"q": "semedli"}
        )
        self.assertEqual([row["id"] for row in tolerant.json()["results"]], [str(self.chair.pk)])

    def test_grant_list_revoke_flow_with_audit(self):
        response = self.post_action(self.head, {"action": "grant", "user": self.chair.pk, "note": "kafedra müdiri"})
        self.assertEqual(response.status_code, 200, response.content)
        grant = RemoteJournalAccess.objects.get(user=self.chair, revoked_at__isnull=True)
        self.assertEqual(grant.granted_by, self.head)
        self.assertTrue(service.has_active_grant(self.chair.pk))

        page = self.client_for(self.head).get(reverse("accounts:profile") + f"?section={SECTION}")
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn("Kamil", html)
        self.assertIn("kafedra müdiri", html)
        self.assertIn("data-rja-revoke", html)

        again = self.post_action(self.head, {"action": "grant", "user": self.chair.pk})
        self.assertEqual(again.status_code, 409)
        marked = self.client_for(self.head).get(
            reverse("accounts:remote_journal_access_candidates"), {"q": "rja_chair"}
        )
        self.assertTrue(marked.json()["results"][0].get("disabled"))

        revoke = self.post_action(self.head, {"action": "revoke", "grant": grant.pk})
        self.assertEqual(revoke.status_code, 200, revoke.content)
        grant.refresh_from_db()
        self.assertIsNotNone(grant.revoked_at)
        self.assertEqual(grant.revoked_by, self.head)
        self.assertFalse(service.has_active_grant(self.chair.pk))
        self.assertEqual(self.post_action(self.head, {"action": "revoke", "grant": grant.pk}).status_code, 409)

        audits = AuditLog.objects.filter(resource_type=service.AUDIT_RESOURCE, resource_id=str(grant.pk))
        self.assertEqual(audits.count(), 2)
        self.assertTrue(audits.filter(user=self.head).count() == 2)

    def test_student_cannot_be_granted(self):
        response = self.post_action(self.head, {"action": "grant", "user": self.student.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "not_eligible")
        self.assertFalse(RemoteJournalAccess.objects.exists())

    def test_regrant_after_revoke_creates_new_row(self):
        first = service.grant(actor=self.head, user_id=self.teacher.pk, organization=self.org)
        service.revoke(actor=self.head, grant_id=first.pk, organization=self.org)
        second = service.grant(actor=self.head, user_id=self.teacher.pk, organization=self.org)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(RemoteJournalAccess.objects.filter(user=self.teacher).count(), 2)
        self.assertTrue(service.has_active_grant(self.teacher.pk))


@override_settings(
    NETWORK_ZONE_ENFORCED=True, INTERNAL_NETWORKS=[], JOURNAL_REMOTE_USER_IDS=(), ADMIN_2FA_REQUIRED=False
)
@patch("apps.accounts.network_zone.temporary_superuser_exempt", return_value=False)
@patch("apps.accounts.network_zone._HttpGateFacts.kind", return_value="teacher")
class NetworkGateTest(_Base):
    def request(self, user, path="/jurnal/"):
        request = RequestFactory().get(path, REMOTE_ADDR="203.0.113.5")
        request.user = User.objects.get(pk=user.pk)
        request.session = {}
        return request

    def middleware(self):
        middleware = NetworkZoneMiddleware(lambda request: HttpResponse("ok"))
        middleware._deny = lambda request, **kwargs: HttpResponse(status=403)
        return middleware

    def test_grant_opens_and_revoke_closes_external_journal(self, *_mocks):
        middleware = self.middleware()
        self.assertEqual(middleware(self.request(self.chair)).status_code, 403)
        grant = service.grant(actor=self.head, user_id=self.chair.pk, organization=self.org)
        self.assertEqual(middleware(self.request(self.chair)).status_code, 200)
        self.assertEqual(middleware(self.request(self.chair, "/accounts/imtahan-bali/")).status_code, 200)
        # Başqa hesaba keçmir.
        self.assertEqual(middleware(self.request(self.teacher)).status_code, 403)
        service.revoke(actor=self.head, grant_id=grant.pk, organization=self.org)
        self.assertEqual(middleware(self.request(self.chair)).status_code, 403)

    def test_env_list_still_works(self, *_mocks):
        with override_settings(JOURNAL_REMOTE_USER_IDS=(str(self.teacher.pk),)):
            self.assertEqual(self.middleware()(self.request(self.teacher)).status_code, 200)
            self.assertTrue(journal_remote_access_allowed(self.request(self.teacher)))
        self.assertFalse(RemoteJournalAccess.objects.exists())

    def test_nginx_auth_endpoint_follows_the_grant(self, *_mocks):
        client = self.client_for(self.chair)
        url = reverse("accounts:journal_remote_auth")
        self.assertEqual(client.get(url).status_code, 403)
        service.grant(actor=self.head, user_id=self.chair.pk, organization=self.org)
        self.assertEqual(client.get(url).status_code, 204)

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_account_still_needs_2fa(self, *_mocks):
        from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY

        with bypass_rls():
            User.objects.filter(pk=self.chair.pk).update(is_staff=True)
        service.grant(actor=self.head, user_id=self.chair.pk, organization=self.org)
        request = self.request(self.chair)
        self.assertFalse(journal_remote_access_allowed(request))
        request.session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = str(self.chair.pk)
        self.assertTrue(journal_remote_access_allowed(request))
