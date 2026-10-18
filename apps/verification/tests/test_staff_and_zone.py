"""Əməkdaş «Sənəd yoxlaması» səhifəsi (403 / 404 / əhatə / ləğv), açar kataloqu və şəbəkə zonası istisnası."""

from __future__ import annotations

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.verification.models import DocumentSeal
from core.rate_limit import _rate_limit_cache
from core.rls import bypass_rls

from .world import PW, build_world, client_for, download_transcript, latest_seal

REASON = "Səhv məlumatla verilib, yenisi ilə əvəz olunub."
ZONE = {
    "NETWORK_ZONE_ENFORCED": True,
    "NETWORK_ZONE_STAFF_INTERNAL_ONLY": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8", "127.0.0.0/8"],
}
EXT = "85.132.1.1"


class StaffPageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkust")
        download_transcript(cls.w)
        download_transcript(cls.w, record=cls.w["record2"])
        cls.seal = latest_seal(subject_user=cls.w["student"])
        cls.seal2 = latest_seal(subject_user=cls.w["s2"])

    def _list(self, user, **params):
        return client_for(self.w["org"], user).get(reverse("verification:staff_list"), params)

    def _revoke(self, user, seal, reason=REASON):
        return client_for(self.w["org"], user).post(
            reverse("verification:staff_revoke", args=[seal.pk]), {"reason": reason}
        )

    def _reload(self, seal):
        with bypass_rls():
            return DocumentSeal.objects.get(pk=seal.pk)

    def test_anonymous_is_sent_to_login(self):
        response = Client().get(reverse("verification:staff_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_missing_key_is_403(self):
        self.assertEqual(self._list(self.w["teacher"]).status_code, 403)
        self.assertEqual(self._revoke(self.w["teacher"], self.seal).status_code, 403)
        self.assertIsNone(self._reload(self.seal).revoked_at)

    def test_teaching_office_lists_and_searches(self):
        response = self._list(self.w["office"])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.seal.code)
        self.assertContains(response, self.seal2.code)
        by_code = self._list(self.w["office"], q=self.seal.code.lower())
        self.assertContains(by_code, self.seal.code)
        self.assertNotContains(by_code, self.seal2.code)
        by_name = self._list(self.w["office"], q="Qurbanov")
        self.assertContains(by_name, self.seal.code)
        self.assertNotContains(by_name, self.seal2.code)

    def test_revoke_requires_a_reason(self):
        response = self._revoke(self.w["office"], self.seal, reason="qısa")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self._reload(self.seal).revoked_at)

    def test_revoke_succeeds_once_and_is_audited(self):
        from apps.audit.models import AuditLog

        self.assertEqual(self._revoke(self.w["office"], self.seal).status_code, 302)
        seal = self._reload(self.seal)
        self.assertIsNotNone(seal.revoked_at)
        self.assertEqual(seal.revoked_by_id, self.w["office"].pk)
        self.assertEqual(seal.revoke_reason, REASON)
        self._revoke(self.w["office"], self.seal, reason="İkinci dəfə ləğv etməyə cəhd edirəm.")
        self.assertEqual(self._reload(self.seal).revoke_reason, REASON)
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="verification.seal", resource_id=self.seal.code, action="update"
                ).exists()
            )
        revoked = self._list(self.w["office"], status="revoked")
        self.assertContains(revoked, self.seal.code)
        self.assertNotContains(revoked, self.seal2.code)

    def test_unit_scoped_holder_sees_only_its_subtree_and_gets_404_outside(self):
        response = self._list(self.w["unit_staff"])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.seal.code)  # G1 ⊂ F1
        self.assertNotContains(response, self.seal2.code)  # G2 ⊂ F2
        self.assertEqual(self._revoke(self.w["unit_staff"], self.seal2).status_code, 404)
        self.assertIsNone(self._reload(self.seal2).revoked_at)

    def test_other_organisation_seal_is_404(self):
        response = client_for(self.w["other"], self.w["other_owner"]).post(
            reverse("verification:staff_revoke", args=[self.seal.pk]), {"reason": REASON}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(self._reload(self.seal).revoked_at)

    def test_view_as_cannot_revoke(self):
        from apps.verification import access

        class _Req:
            is_view_as = True

        self.assertTrue(access.is_read_only(_Req()))

    def test_permission_is_in_catalog_and_role_template(self):
        from apps.organizations.models import Role
        from apps.organizations.public import get_all_permissions

        self.assertIn("document_seal.manage", get_all_permissions())
        with bypass_rls():
            role = Role.objects.get(organization=self.w["org"], name="teaching_office_staff")
            teacher_role = Role.objects.get(organization=self.w["org"], name="teacher")
        self.assertIn("document_seal.manage", role.permissions)
        self.assertNotIn("document_seal.manage", teacher_role.permissions or [])

    def test_sidebar_item_follows_the_capability_flag(self):
        from django.template.loader import render_to_string

        item = "accounts/profile/sidebar/items/_document_seals.html"
        shown = render_to_string(item, {"role_capabilities": {"can_manage_document_seals": True}})
        hidden = render_to_string(item, {"role_capabilities": {"can_manage_document_seals": False}})
        self.assertIn(reverse("verification:staff_list"), shown)
        self.assertNotIn("href", hidden)


class NetworkZoneTest(TestCase):
    """`/yoxla/` kənar zonadan HƏR KƏSƏ açıqdır (inzibati hesab daxil); əməkdaş siyahısı isə qapalı qalır."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkunz")
        download_transcript(cls.w)
        cls.seal = latest_seal(subject_user=cls.w["student"])

    def setUp(self):
        cache.clear()
        _rate_limit_cache().clear()

    def test_prefix_is_in_the_open_list(self):
        from apps.accounts import network_zone

        self.assertIn("/yoxla/", network_zone._ALWAYS_OPEN_PREFIXES)
        self.assertTrue(network_zone._is_open_path(reverse("verification:detail", args=[self.seal.code])))
        self.assertFalse(network_zone._is_open_path(reverse("verification:staff_list")))

    @override_settings(**ZONE)
    def test_anonymous_outside_can_verify(self):
        response = Client().get(reverse("verification:detail", args=[self.seal.code]), REMOTE_ADDR=EXT)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sənəd etibarlıdır")

    @override_settings(**ZONE)
    def test_staff_outside_can_verify_but_not_open_the_staff_list(self):
        client = Client()
        self.assertTrue(client.login(username=self.w["office"].username, password=PW))
        session = client.session
        session["active_organization"] = self.w["org"].slug
        session.save()
        verify = client.get(reverse("verification:detail", args=[self.seal.code]), REMOTE_ADDR=EXT)
        self.assertEqual(verify.status_code, 200)
        staff = client.get(reverse("verification:staff_list"), REMOTE_ADDR=EXT)
        self.assertEqual(staff.status_code, 403)
        inside = client.get(reverse("verification:staff_list"), REMOTE_ADDR="10.0.2.50")
        self.assertEqual(inside.status_code, 200)
