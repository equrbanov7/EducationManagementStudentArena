"""«Jurnal təmizliyi» kabinet bölməsi — RBAC, JSON endpoint-ləri və tam axın (sahib 2026-10-10).

Kilidlənən qaydalar:

* menyu bəndi və panel YALNIZ RİM rəhbəri (``ikt_rehber``) və superadmin üçündür; dekan / rektor / müəllim
  paneli görmür, oxu endpoint-i ``has_access: false`` + boş data qaytarır, yazı endpoint-i 403 verir;
* RİM rəhbəri HTTP üzərindən önizləmə → tətbiq → tarixçə → «Bərpa et» axınını keçir; qısa səbəb və naməlum
  əməl rədd olunur;
* siyahı endpoint-inin sorğu sayı sətir sayından asılı deyil.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar.models import AcademicStatus, Enrollment, JournalHygieneDecision
from apps.registrar.tests.journal_hygiene_fixture import REASON, HygieneBase, User
from core.rls import bypass_rls

SECTION = "journal-hygiene"


@override_settings(UNIVERSITY_MODE=True)
class JournalHygieneSectionTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.rim = cls._member("jh_rim", "ikt_rehber")
            cls.dean = cls._member("jh_dean", "dean")
            cls.rector = cls._member("jh_rector", "rector")
            cls.superadmin = User.objects.create_superuser("jh_su", "jh_su@qku.edu.az", "pw")
            cls.row = cls.enroll(cls.make_student("jh_sx", status=AcademicStatus.EXPELLED))
            cls.empty_row = cls.enroll(cls.make_student("jh_se"), cls._offering(cls.subject_c, cls.past))

    @classmethod
    def _member(cls, username, role):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
        )
        return user

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _rows(self, client, **params):
        return client.get(reverse("accounts:journal_hygiene_rows"), params)

    def _act(self, client, **payload):
        return client.post(
            reverse("accounts:journal_hygiene_action"), data=json.dumps(payload), content_type="application/json"
        )

    def test_hidden_and_refused_for_other_roles(self):
        for user in (self.dean, self.rector, self.teacher):
            with self.subTest(user=user.username):
                client = self._client(user)
                page = client.get(reverse("accounts:profile"), {"section": SECTION})
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, f'data-profile-section-panel="{SECTION}"')
                self.assertNotContains(page, f'data-section="{SECTION}"')
                data = self._rows(client, tab="left").json()
                self.assertFalse(data["has_access"])
                self.assertEqual(data["results"], [])
                response = self._act(client, action="preview", tab="left", ids=[str(self.row.pk)], target="suspend")
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.status_of(self.row), Enrollment.Status.ENROLLED)

    def test_visible_for_rim_head_and_superadmin(self):
        page = self._client(self.rim).get(reverse("accounts:profile"), {"section": SECTION})
        self.assertContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertContains(page, f'data-section="{SECTION}"')
        self.assertContains(page, "data-jh-root")
        self.assertContains(page, "journal_hygiene.js")
        fragment = self._client(self.rim).get(reverse("accounts:profile_section_fragment", args=[SECTION]))
        self.assertEqual(fragment.status_code, 200)
        self.assertContains(fragment, "data-jh-root")
        for user in (self.rim, self.superadmin):
            data = self._rows(self._client(user), tab="left").json()
            self.assertTrue(data["has_access"])
            self.assertTrue(data["can_apply"])

    def test_lists_counts_and_select_all(self):
        client = self._client(self.rim)
        left = self._rows(client, tab="left").json()
        self.assertEqual([row["id"] for row in left["results"]], [str(self.row.pk)])
        self.assertEqual(left["counts"]["total"], 1)
        self.assertEqual(left["results"][0]["reason"], "expelled")
        empty = self._rows(client, tab="empty").json()
        self.assertEqual([row["id"] for row in empty["results"]], [str(self.empty_row.pk)])
        self.assertEqual(self._rows(client, tab="history").json()["total"], 0)
        self.assertEqual(self._rows(client, tab="left", select="all").json()["ids"], [str(self.row.pk)])
        self.assertEqual(self._rows(client, tab="left", page="x", period="bad-id").status_code, 200)

    def test_preview_apply_history_and_revert_over_http(self):
        client = self._client(self.rim)
        ids = [str(self.row.pk)]
        preview = self._act(client, action="preview", tab="left", ids=ids, target="suspend").json()
        self.assertTrue(preview["ok"] and preview["can_apply"])
        short = self._act(client, action="apply", tab="left", ids=ids, target="suspend", reason="qısa", digest="x")
        self.assertEqual((short.status_code, short.json()["error"]), (400, "reason_too_short"))
        applied = self._act(
            client, action="apply", tab="left", ids=ids, target="suspend", reason=REASON, digest=preview["digest"]
        )
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["changed"], 1)
        self.assertEqual(self.status_of(self.row), Enrollment.Status.SUSPENDED)

        history = self._rows(client, tab="history").json()
        self.assertEqual(history["total"], 1)
        entry = history["results"][0]
        self.assertTrue(entry["can_revert"])
        self.assertEqual((entry["from_status"], entry["to_status"]), ("enrolled", "suspended"))
        reverted = self._act(client, action="revert", ids=[entry["id"]], reason=REASON)
        self.assertEqual(reverted.status_code, 200)
        self.assertEqual(self.status_of(self.row), Enrollment.Status.ENROLLED)
        with bypass_rls():
            self.assertIsNotNone(JournalHygieneDecision.objects.get(pk=entry["id"]).reverted_at)
        self.assertEqual(self._act(client, action="delete", ids=ids).status_code, 400)

    def test_rows_endpoint_query_count_is_flat(self):
        client = self._client(self.rim)
        self._rows(client, tab="left")  # sessiya / keş isinməsi

        def run():
            with CaptureQueriesContext(connection) as ctx:
                response = self._rows(client, tab="left")
            return len(ctx.captured_queries), response.json()["total"]

        small, total_small = run()
        with bypass_rls():
            for index in range(5):
                self.enroll(self.make_student(f"jh_sq{index}", status=AcademicStatus.EXPELLED))
        large, total_large = run()
        self.assertEqual(total_large, total_small + 5)
        self.assertEqual(small, large)
