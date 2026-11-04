"""Sahib 2026-11-04 — «Dondur» səbəb kateqoriyası insan səthlərində (endpoint, çekmecə, «İnsanlar» kartı).

Domen qaydası və jurnaldan gizlənmə: ``apps/registrar/tests/test_freeze_leave_reasons_2026_11_04.py``.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.services import people
from apps.accounts.services.rim.policy import RimAccessError
from apps.audit.models import AuditLog
from apps.registrar.leave_reasons import LeaveReason
from apps.registrar.models import AcademicStatus, StudentMovement
from core.rls import bypass_rls

from .test_people_academic import AcademicFixture, _request
from .test_student_services_sections import StudentServicesBase

LEAVE = {"kind": "academic_leave", "target_group": "", "effective_until": "2030-06-30", "reason": ""}


class FreezeEndpointTest(StudentServicesBase):
    def test_missing_category_is_rejected_and_nothing_changes(self):
        response = self._post_movement(**LEAVE)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "leave_reason_required")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ENROLLED)
        self.assertFalse(StudentMovement.objects.exists())

    def test_unknown_category_is_rejected(self):
        response = self._post_movement(**LEAVE, leave_reason="vacation")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "leave_reason_unknown")

    def test_other_requires_a_note(self):
        response = self._post_movement(**LEAVE, leave_reason="other")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "leave_reason_note_required")

        payload = dict(LEAVE, reason="Xaricdə mübadilə proqramı")
        response = self._post_movement(**payload, leave_reason="other")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(StudentMovement.objects.get().leave_reason, "other")

    def test_category_is_stored_returned_and_audited(self):
        response = self._post_movement(**LEAVE, leave_reason="childcare")
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()["movement"]
        self.assertEqual(row["leave_reason"], "childcare")
        self.assertEqual(row["leave_reason_label"], str(LeaveReason.CHILDCARE.label))
        self.assertIn(str(LeaveReason.CHILDCARE.label), row["to_label"])

        movement = StudentMovement.objects.get()
        self.assertEqual((movement.kind, movement.leave_reason), ("academic_leave", "childcare"))
        self.assertEqual(movement.effective_until, date(2030, 6, 30))
        entry = AuditLog.objects.get(resource_type="accounts.people.movement")
        self.assertEqual(entry.changes["leave_reason"], "childcare")
        self.assertEqual(entry.changes["leave_reason_label"], str(LeaveReason.CHILDCARE.label))
        self.assertEqual(entry.new_values["leave_reason"], "childcare")

        # Tələbə kartının «Hərəkət tarixçəsi» də kateqoriyanı göstərir.
        url = reverse("accounts:student_registry_card", kwargs={"record_id": self.record.pk})
        history = self._client("student_services").get(url).json()["movements"]
        self.assertEqual(history[0]["leave_reason_label"], str(LeaveReason.CHILDCARE.label))

    def test_category_is_ignored_for_other_movements(self):
        response = self._post_movement(leave_reason="medical")  # qrup köçürməsi
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(StudentMovement.objects.get().leave_reason, "")

    def test_registry_dialog_offers_the_categories(self):
        response = self._fragment("student_services", "student-registry")
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn('name="leave_reason"', html)
        self.assertIn('data-sr-need="leave_reason"', html)
        for choice in LeaveReason:
            self.assertIn(f'value="{choice.value}"', html)
        kinds = {kind["key"]: kind for kind in response.context["student_registry_section"]["movement_kinds"]}
        self.assertTrue(kinds["academic_leave"]["requires_leave_reason"])
        self.assertFalse(kinds["expulsion"]["requires_leave_reason"])

    def test_groups_drawer_freeze_dialog_requires_the_category(self):
        response = self._fragment("ikt_rehber", "groups-registry")
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        start = html.index('id="tofStudentFreezeDialog"')
        dialog = html[start : html.index("</form>", start)]
        self.assertIn('name="leave_reason"', dialog)
        self.assertIn("data-leave-reason-select data-ems-required", dialog)
        self.assertIn(f'value="{LeaveReason.OTHER.value}"', dialog)


class PeopleStatusFreezeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self):
        return people.resolve_actor(_request(self.fx.dean_m, self.fx.org))

    def _set(self, **extra):
        with bypass_rls():
            return people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="academic_leave",
                reason="Tələbənin ərizəsi və həkim arayışı əsasında",
                **extra,
            )

    def test_category_is_required(self):
        with self.assertRaises(RimAccessError) as ctx:
            self._set()
        self.assertEqual(ctx.exception.reason_code, "leave_reason_required")
        with bypass_rls():
            self.fx.record_a.refresh_from_db()
        self.assertEqual(self.fx.record_a.status, "enrolled")

    def test_category_is_audited(self):
        result = self._set(leave_reason="medical")
        self.assertEqual(result["leave_reason"], "medical")
        with bypass_rls():
            entry = AuditLog.objects.filter(resource_type="accounts.people.academic").order_by("-created_at").first()
        self.assertEqual(entry.changes["leave_reason"], "medical")
        self.assertEqual(entry.changes["leave_reason_label"], str(LeaveReason.MEDICAL.label))
        self.assertEqual(entry.new_values, {"status": "academic_leave", "leave_reason": "medical"})
