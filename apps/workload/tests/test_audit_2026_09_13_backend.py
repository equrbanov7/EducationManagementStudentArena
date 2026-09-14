"""Backend auditi 2026-09-13 — F-01 (workload JSON endpoint-lərində qeyri-UUID pk → 500).

Auditorun probu (``scratchpad/audit/backend/probes/test_backend_probes.py::
MalformedInputProbes::test_m01/m02``) sandbox-da ``workload:assign`` və
``workload:row_save`` üçün ``row_id="abc"`` ilə HTTP 500 aldı. İndi pk-lar
``core.http_ids.parse_uuid`` ilə süzülür və pozuq dəyər «tapılmadı» (404) verir.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.constants import RoleScopeType
from core.http_ids import parse_int, parse_uuid

from .factories import activate_member, make_org, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class HttpIdsHelperTest(SimpleTestCase):
    """``core/http_ids.py`` — ortaq pk parse köməkçisi."""

    def test_parse_uuid_accepts_uuid_objects_and_strings_only(self):
        value = uuid.uuid4()
        self.assertEqual(parse_uuid(value), value)
        self.assertEqual(parse_uuid(str(value)), value)
        self.assertEqual(parse_uuid(f"  {value}  "), value)
        for bad in ("abc", "", None, 12, "not-a-uuid", ["x"], {"a": 1}):
            self.assertIsNone(parse_uuid(bad), repr(bad))

    def test_parse_int_rejects_bool_float_and_garbage(self):
        self.assertEqual(parse_int("42"), 42)
        self.assertEqual(parse_int(" 7 "), 7)
        self.assertEqual(parse_int(3), 3)
        for bad in ("abc", "", None, True, False, "7.5", "1e3", "NaN"):
            self.assertIsNone(parse_int(bad), repr(bad))


class WorkloadNonUuidPkTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-f01")
        self.stack = make_structure(self.org, code="F01")
        self.head = User.objects.create_user("f01_head", "f01_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self.client.force_login(self.head)

    def _post(self, name, payload):
        return self.client.post(reverse(name), data=json.dumps(payload), content_type="application/json")

    def test_assign_with_non_uuid_row_id_is_404_not_500(self):
        response = self._post("workload:assign", {"row_id": "not-a-uuid", "teacher_id": "x"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "workload.row_not_found")

    def test_row_save_with_non_uuid_ids_is_not_500(self):
        response = self._post("workload:row_save", {"row_id": "abc", "task_id": "abc"})
        self.assertLess(response.status_code, 500)
        self.assertFalse(response.json()["ok"])

    def test_row_save_with_non_uuid_row_id_on_real_task_is_404(self):
        response = self._post("workload:row_save", {"row_id": "abc", "task_id": str(self.task.pk)})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "workload.row_not_found")

    def test_row_delete_unassign_confirm_with_garbage_ids_are_not_500(self):
        for name, payload in (
            ("workload:row_delete", {"row_id": "zzz", "task_id": str(self.task.pk)}),
            ("workload:unassign", {"assignment_id": "zzz"}),
            ("workload:confirm", {"task_id": "zzz"}),
            ("workload:amend", {"task_id": "zzz"}),
        ):
            response = self._post(name, payload)
            self.assertLess(response.status_code, 500, name)
            self.assertFalse(response.json()["ok"], name)

    def test_assign_with_non_uuid_assignment_id_is_404(self):
        from .factories import make_row

        row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
        response = self._post("workload:assign", {"row_id": str(row.pk), "assignment_id": "abc"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "workload.assignment_not_found")
