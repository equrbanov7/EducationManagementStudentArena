"""«Alt qrupa tələbə əlavə et» aləti — HTTP səthi, icazələr, menyu, kabinet kredit yükü (sahib 2026-10-18).

Qapılar açarladır (``retake.manage``), rol adı ilə yox: açarsız aktor 403, əhatədən kənar tələbə 404,
view-as rejimində yazı 403. Sənəd validasiyası, toqquşma təsdiqi, geri götürmə və sorğu büdcələri.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar.models import Enrollment, SubgroupPlacementEvent
from apps.registrar.tests.subgroup_base import SubgroupFixture, pdf
from core.rls import bypass_rls

REASON = "Dekanlığın təqdimatı əsasında alt qrupa yerləşdirmə"


class _ToolBase(SubgroupFixture, TestCase):
    PREFIX = "sgt"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def post_place(self, client, **extra):
        data = {
            "student": str(self.student.pk),
            "offering": str(self.physics_g1.pk),
            "reason": REASON,
            "document": pdf(),
        }
        data.update(extra)
        data = {key: value for key, value in data.items() if value is not None}
        return client.post(reverse("accounts:subgroup_placement_place"), data)


class PermissionTest(_ToolBase):
    def test_get_endpoints_require_key(self):
        client = self.client_for(self.plain)
        for name in ("subgroup_placement_students", "subgroup_placement_recent"):
            self.assertEqual(client.get(reverse("accounts:" + name)).status_code, 403, name)
        self.assertEqual(self.post_place(client).status_code, 403)

    def test_teacher_and_student_are_forbidden(self):
        for user in (self.teacher, self.student):
            response = self.client_for(user).get(reverse("accounts:subgroup_placement_students"))
            self.assertEqual(response.status_code, 403)

    def test_out_of_scope_student_is_404(self):
        client = self.client_for(self.far_dean)
        url = reverse("accounts:subgroup_placement_student", args=[self.student.pk])
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(self.post_place(client).status_code, 404)

    def test_student_search_is_scoped(self):
        data = self.client_for(self.dean).get(reverse("accounts:subgroup_placement_students")).json()
        ids = {row["id"] for row in data["results"]}
        self.assertIn(str(self.student.pk), ids)
        self.assertNotIn(str(self.far_student.pk), ids)
        org_wide = self.client_for(self.org_admin).get(reverse("accounts:subgroup_placement_students")).json()
        self.assertIn(str(self.far_student.pk), {row["id"] for row in org_wide["results"]})

    def test_menu_visibility_follows_key(self):
        from apps.accounts.views._helpers.rbac_sections import apply_permission_section_gates

        for user, expected in ((self.dean, True), (self.org_admin, True), (self.plain, False), (self.teacher, False)):
            sections: set = set()
            apply_permission_section_gates(user, self.org, sections, is_superadmin=False, is_owner=False)
            self.assertEqual("subgroup-placement" in sections, expected, user.username)


class FlowTest(_ToolBase):
    def test_summary_subjects_offerings_preview(self):
        client = self.client_for(self.dean)
        summary = client.get(reverse("accounts:subgroup_placement_student", args=[self.student.pk])).json()
        self.assertEqual(summary["group"], "G2")
        self.assertEqual(summary["credit"]["total"], 10)
        subjects = client.get(reverse("accounts:subgroup_placement_subjects"), {"student": self.student.pk}).json()
        self.assertIn(str(self.physics.pk), {row["id"] for row in subjects["results"]})
        offerings = client.get(
            reverse("accounts:subgroup_placement_offerings"), {"student": self.student.pk, "subject": self.physics.pk}
        ).json()
        self.assertEqual([row["id"] for row in offerings["offerings"]], [str(self.physics_g1.pk)])
        self.assertEqual(offerings["offerings"][0]["projection"]["total_after"], 16)
        preview = client.get(
            reverse("accounts:subgroup_placement_preview"), {"student": self.student.pk, "offering": self.physics_g1.pk}
        ).json()
        self.assertTrue(preview["ok"], preview)

    def test_place_and_undo_over_http(self):
        client = self.client_for(self.dean)
        response = self.post_place(client)
        self.assertEqual(response.status_code, 200, response.content)
        event_id = response.json()["event_id"]
        recent = client.get(reverse("accounts:subgroup_placement_recent")).json()
        self.assertEqual([row["id"] for row in recent["results"]], [event_id])
        undo = client.post(
            reverse("accounts:subgroup_placement_undo"),
            data={"event": event_id, "reason": "Səhv yerləşdirmə — geri götürülür"},
            content_type="application/json",
        )
        self.assertEqual(undo.status_code, 200, undo.content)
        with bypass_rls():
            self.assertEqual(
                Enrollment.objects.get(student=self.student, offering=self.physics_g1).status, Enrollment.Status.DROPPED
            )
            self.assertEqual(SubgroupPlacementEvent.objects.count(), 2)
        recent = client.get(reverse("accounts:subgroup_placement_recent")).json()
        self.assertTrue(recent["results"][0]["undone"])

    def test_document_validation_over_http(self):
        client = self.client_for(self.dean)
        fake = SimpleUploadedFile("teqdimat.png", b"not an image at all", content_type="image/png")
        response = self.post_place(client, document=fake)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "document_invalid")
        response = self.post_place(client, document=None)
        self.assertEqual(response.json()["error"], "document_required")
        response = self.post_place(client, document=None, order_number="Əmr 12", order_date="2025-09-12")
        self.assertEqual(response.status_code, 200, response.content)

    def test_clash_requires_explicit_confirmation(self):
        self.slot(self.own_math, weekday=1, start=(9, 0), end=(10, 20))
        self.slot(self.physics_g1, weekday=1, start=(9, 30), end=(10, 50))
        client = self.client_for(self.dean)
        response = self.post_place(client)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "clash_confirm_required")
        response = self.post_place(client, accept_clash="1")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([w["code"] for w in response.json()["warnings"]], ["schedule_clash"])

    def test_failure_code_is_returned(self):
        client = self.client_for(self.dean)
        response = self.post_place(client, offering=str(self.own_history.pk))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "own_group")

    def test_view_as_cannot_write(self):
        from unittest import mock

        from apps.accounts.views.subgroup_placement import policy

        actor = policy.PlacementActor(
            user=self.dean, organization=self.org, has_access=True, can_write=False, view_as=True
        )
        with (
            mock.patch.object(policy, "resolve_actor", return_value=actor),
            mock.patch("apps.accounts.views.subgroup_placement.actions.resolve_actor", return_value=actor),
        ):
            response = self.post_place(self.client_for(self.dean))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "view_as")


class PanelAndCabinetTest(_ToolBase):
    def test_panel_renders_for_key_holder(self):
        response = self.client_for(self.dean).get(reverse("accounts:profile"), {"section": "subgroup-placement"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-sgp-root", html)
        self.assertIn('id="sgp-i18n"', html)
        self.assertIn("subgroup_placement.js", html)

    def test_panel_hidden_without_key(self):
        response = self.client_for(self.plain).get(reverse("accounts:profile"), {"section": "subgroup-placement"})
        self.assertNotIn("data-sgp-root", response.content.decode())

    @override_settings(UNIVERSITY_MODE=True)
    def test_student_cabinet_shows_semester_credit(self):
        client = self.client_for(self.dean)
        self.post_place(client)
        response = self.client_for(self.student).get(reverse("accounts:profile"), {"section": "my-subjects"})
        html = response.content.decode()
        self.assertIn('data-credit-load="16/36"', html)

    def test_registry_card_has_trail(self):
        from django.contrib.auth import get_user_model

        self.post_place(self.client_for(self.dean))
        admin = get_user_model().objects.create_superuser("sgt_root", "sgt_root@qku.edu.az", "pw")
        with bypass_rls():
            record_id = self.record.pk
        response = self.client_for(admin).get(reverse("accounts:student_registry_card", args=[record_id]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["semester_credit"]["total"], 16)
        self.assertEqual(len(payload["subgroup_placements"]), 1)
        self.assertIn("section=subgroup-placement", payload["subgroup_placement_url"])


class QueryBudgetTest(_ToolBase):
    def test_recent_list_is_constant(self):
        admin = self.client_for(self.org_admin)
        self.post_place(self.client_for(self.dean))
        admin.get(reverse("accounts:subgroup_placement_recent"))  # isinmə (sessiya / üzvlük keşi)
        with CaptureQueriesContext(connection) as one:
            first = admin.get(reverse("accounts:subgroup_placement_recent")).json()
        response = self.post_place(admin, student=str(self.far_student.pk))
        self.assertEqual(response.status_code, 200, response.content)
        with CaptureQueriesContext(connection) as two:
            second = admin.get(reverse("accounts:subgroup_placement_recent")).json()
        self.assertEqual((len(first["results"]), len(second["results"])), (1, 2))
        self.assertEqual(len(one), len(two))

    def test_student_search_is_constant(self):
        client = self.client_for(self.org_admin)
        client.get(reverse("accounts:subgroup_placement_students"))  # isinmə (sessiya / üzvlük keşi)
        with CaptureQueriesContext(connection) as small:
            client.get(reverse("accounts:subgroup_placement_students"), {"limit": 1})
        with CaptureQueriesContext(connection) as large:
            client.get(reverse("accounts:subgroup_placement_students"), {"limit": 20})
        self.assertEqual(len(small), len(large))
