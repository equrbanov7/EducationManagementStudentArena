"""Şəxs kartı (people detail drawer) — QA 2026-09-05 P1-2 reqressiya qapısı.

1. **Üzvlük əhatəsi.** Vahid-əhatəli aktor (dekan) hədəf tələbənin təşkilat-səviyyəli
   (``scope_unit=None``) üzvlüyünü GÖRMƏLİDİR — əvvəl ``scope_memberships_by_unit``
   onu süzürdü və kart boş gəlirdi. Vahidli üzvlük (kafedra) isə alt-ağac içindədirsə
   görünür.
2. **Drawer markup-ı.** Kataloq bölməsi ems_ui drawer-ini (``.ems-overlay--drawer``)
   və JS üçün i18n JSON blokunu render edir; ``people_detail.js`` qabıqda yüklənir.
"""

from __future__ import annotations

import json
import re

from django.test import Client, RequestFactory, TestCase

from apps.accounts.services import people
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


class DetailMembershipScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _detail(self, actor_user, target):
        actor = people.resolve_actor(_request(actor_user, self.fx.org))
        with bypass_rls():
            return people.build_detail(actor=actor, user_id=target.pk)

    def test_dean_sees_students_org_wide_membership(self):
        detail = self._detail(self.fx.dean_a, self.fx.student_a)
        roles = {m["role_name"] for m in detail["person"]["memberships"]}
        self.assertIn(self.fx.role_student.name, roles, detail["person"]["memberships"])

    def test_dean_sees_teachers_chair_membership_inside_own_faculty(self):
        detail = self._detail(self.fx.dean_a, self.fx.teacher_a)
        roles = {m["role_name"] for m in detail["person"]["memberships"]}
        self.assertIn(self.fx.role_teacher.name, roles, detail["person"]["memberships"])

    def test_rector_sees_everything(self):
        detail = self._detail(self.fx.rector, self.fx.student_b)
        self.assertTrue(detail["person"]["memberships"], "org-səviyyəli aktor üçün üzvlüklər boş olmamalıdır")


class DrawerMarkupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def test_students_section_renders_ems_drawer_and_i18n_block(self):
        client = Client()
        client.force_login(self.fx.dean_a)
        response = client.get("/accounts/profile/?section=people-students", follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("people_detail.js", html)
        overlay = re.search(
            r'<div class="ems-overlay ems-overlay--drawer" id="people-detail-students" data-people-detail-modal hidden>',
            html,
        )
        self.assertIsNotNone(overlay, "drawer konteyneri yoxdur")
        self.assertIn('data-people-detail-body tabindex="-1"', html)
        self.assertIn("data-ems-overlay-close", html)
        block = re.search(
            r'<script type="application/json" id="people-detail-i18n-students">(.*?)</script>', html, re.S
        )
        self.assertIsNotNone(block, "i18n JSON bloku yoxdur")
        data = json.loads(block.group(1))
        for key in ("memberships", "academic", "teaching", "actions", "status", "gender_labels"):
            self.assertIn(key, data)
        self.assertNotIn("people__modal", html, "köhnə modal markup-ı qalmamalıdır")
