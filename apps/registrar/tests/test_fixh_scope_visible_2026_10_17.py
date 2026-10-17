"""Review 2026-10-17 (FIX-H): «Uyğun vaxtlar» toqquşmanın əhatəsini AÇILIŞ səviyyəsində yoxlayır; redaktor 404-ləri.

Əvvəl ``scope_visible`` sərt ``scoped_groups`` (qrup id-ləri) idi — kafedranın öz fənninin başqa qrupdakı dərsi
«əhatədən kənar» görünürdü, saxlama-öncəsi yoxlama (``schedule_editor.scope_filter``) isə onu əhatədə sayırdı.
İndi əhatə qrupunda OLMAYAN dərs üçün açılış səviyyəsində ``can_manage_offering`` soruşulur (açılış üzrə keşlə);
əhatə qrupu sürətli yoldur (bir sorğu — sorğu sayı slot sayından asılı deyil).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.organizations.models import OrgUnit
from apps.registrar import schedule_suggest
from apps.registrar.tests.test_schedule_slot_instructor_editor import _EditorBase
from core.constants import OrgUnitType
from core.rls import bypass_rls


class ScopeVisibleTest(SimpleTestCase):
    def test_no_actor_means_no_filter(self):
        self.assertIsNone(schedule_suggest.scope_visible(None, object()))

    def test_offering_level_and_cached_per_offering(self):
        allowed = {"o1"}
        calls = []

        def fake(actor, organization, offering):
            calls.append(offering.pk)
            return offering.pk in allowed

        def slot(offering_id, group_id="g-out"):
            return SimpleNamespace(offering_id=offering_id, offering=SimpleNamespace(pk=offering_id, group_id=group_id))

        groups = mock.Mock()
        groups.values_list.return_value = ["g-in"]
        with (
            mock.patch("apps.registrar.schedule_manage.scoped_groups", return_value=groups),
            mock.patch("apps.registrar.schedule_manage.can_manage_offering", side_effect=fake),
        ):
            visible = schedule_suggest.scope_visible(object(), object())
            results = [visible(slot("o1")), visible(slot("o2")), visible(slot("o1")), visible(slot("o2"))]
            in_scope_group = visible(slot("o3", "g-in"))
        self.assertEqual(results, [True, False, True, False])
        self.assertEqual(calls, ["o1", "o2"])  # əhatə qrupundan kənar açılış başına bir yoxlama
        self.assertTrue(in_scope_group)  # əhatə qrupu — sürətli yol, sorğusuz
        self.assertNotIn("o3", calls)


# ── QA-2 F-09: redaktorda əhatədən kənar / olmayan qrup və dərs → 404 (açar yoxdursa 403) ─────────────────


class EditorNotFoundTest(_EditorBase):
    code = "fxhnf"

    def test_deleted_or_unknown_slot_is_404(self):
        missing = "00000000-0000-0000-0000-000000000000"
        for action in ("delete", "move", "check_move"):
            with self.subTest(action=action):
                response = self._act(self.coordinator, {**self._payload(), "action": action, "slot_id": missing})
                self.assertEqual(response.status_code, 404, response.content)
                self.assertEqual(response.json()["error"], "not_found")

    def test_out_of_scope_group_is_404_for_check_plan_and_save(self):
        with bypass_rls():
            far = OrgUnit.objects.create(
                organization=self.org, name="Uzaq", slug=f"{self.code}-far", unit_type=OrgUnitType.FACULTY
            )
            far_group = OrgUnit.objects.create(
                organization=self.org, parent=far, name="999F", slug=f"{self.code}-999f", unit_type=OrgUnitType.GROUP
            )
        for action in ("check", "plan", "save"):
            with self.subTest(action=action):
                payload = {**self._payload(group_id=str(far_group.pk)), "action": action}
                self.assertEqual(self._act(self.coordinator, payload).status_code, 404)

    def test_missing_key_is_still_403(self):
        self.assertEqual(self._act(self.teacher_a, {**self._payload(), "action": "check"}).status_code, 403)
