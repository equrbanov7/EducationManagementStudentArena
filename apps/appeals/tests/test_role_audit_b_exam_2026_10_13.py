"""Rol auditi 2026-10-13 B1 — apellyasiya QƏRARI açarla (``appeal.respond`` + ``appeal.decide``).

Əvvəl ``is_exam_center_user`` (rol adı) kifayət edirdi: imtahan mərkəzi işçisi və RİM əməkdaşı (alias
``exam_center_staff``) da bal dəyişən qəbul/rədd verirdi. İndi onlar apellyasiyanı AÇIR (yalnız-oxu),
qərar POST-u 403-dür; rəhbər (şablonda açarlar var) əvvəlki kimi qərar verir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.appeals.constants import APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_PENDING
from apps.appeals.models import AppealItem
from apps.appeals.tests.test_audit_2026_09_28_a3 import _A3Setup
from apps.organizations.models import Membership
from core.rls import bypass_rls

User = get_user_model()
_AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class AppealDecisionKeyTests(_A3Setup):
    def setUp(self):
        super().setUp()
        self.users = {}
        with bypass_rls():
            for role_name in ("exam_center_staff", "rim_staff", "exam_center_head"):
                user = User.objects.create_user(f"b1_{role_name}", f"b1_{role_name}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                self.users[role_name] = user
        attempt, question, answer = self._written_attempt(checked=True, teacher_score=5)
        self.item = self._item(attempt, question, answer)
        self.url = reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1"

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _decide(self, client):
        return client.post(
            self.url, {f"decision_{self.item.id}": "accept", f"response_{self.item.id}": "Haqlıdır."}, **_AJAX
        )

    def test_staff_and_rim_staff_view_read_only_but_cannot_decide(self):
        for role_name in ("exam_center_staff", "rim_staff"):
            with self.subTest(role=role_name):
                client = self._client(self.users[role_name])
                listing = client.get(reverse("appeals:manage_appeals") + "?fragment=1", **_AJAX)
                self.assertEqual(listing.status_code, 200)
                detail = client.get(self.url, **_AJAX)
                self.assertEqual(detail.status_code, 200)
                self.assertFalse(detail.context["review_can_decide"])
                self.assertContains(detail, "Yalnız baxış rejimi")
                self.assertNotContains(detail, f'name="decision_{self.item.id}"')

                response = self._decide(client)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(response.json()["ok"])
                self.item.refresh_from_db()
                self.assertEqual(self.item.status, APPEAL_ITEM_STATUS_PENDING)

    def test_head_decides(self):
        client = self._client(self.users["exam_center_head"])
        detail = client.get(self.url, **_AJAX)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.context["review_can_decide"])
        response = self._decide(client)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(AppealItem.objects.get(pk=self.item.pk).status, APPEAL_ITEM_STATUS_ACCEPTED)

    def test_head_without_decide_key_is_read_only(self):
        # Redaktor həqiqidir: rəhbərdən `appeal.decide` alınsa qərar da bağlanır (rol adı kifayət deyil).
        with bypass_rls():
            role = self.org.roles.get(name="exam_center_head")
            role.permissions = [perm for perm in role.permissions if perm != "appeal.decide"]
            role.save(update_fields=["permissions"])
        response = self._decide(self._client(self.users["exam_center_head"]))
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, APPEAL_ITEM_STATUS_PENDING)
