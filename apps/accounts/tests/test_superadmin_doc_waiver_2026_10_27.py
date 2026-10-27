"""Superadmin sənədsiz düzəliş (sahib 2026-10-27) — tələbə hərəkəti əmri + interfeys.

* Superadmin «Hərəkət əmri»ni əmr № / tarix / səbəb YAZMADAN verir: ledger-ə «SA-…» əmri + bugünkü tarix, səbəbə
  «Superadmin düzəlişi — sənədsiz (ad, tarix)» düşür; audit sətrində ``superadmin_document_waiver = True``.
  Rəsmi köçürmə servisi (DB trigger-i, tarixçə) yenə işləyir — qrup həqiqətən dəyişir.
* Adi rol (Tələbə Xidmətləri) üçün əmr nömrəsi və tarixi YENƏ məcburidir.
* Dialoqda superadmin üçün «*» və ``data-ems-required`` yoxdur, izah mətni var; adi rolda əvvəlki kimi.
"""

from __future__ import annotations

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.context_processors import view_as_context
from apps.audit.models import AuditLog
from apps.registrar.models import StudentMovement
from core import superadmin_waiver

from .test_student_services_sections import StudentServicesBase, User


class MovementWaiverTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_user(
            "ss_sa_admin", "ss_sa_admin@qku.edu.az", "pw", is_superuser=True, first_name="Elvin", last_name="Sahib"
        )

    def _admin_client(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_superadmin_transfers_without_order_or_reason(self):
        response = self._admin_client().post(
            reverse("accounts:student_registry_action"),
            self._movement_payload(order_number="", order_date="", reason=""),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group_b.pk)  # rəsmi köçürmə servisi işlədi
        movement = StudentMovement.objects.get(record=self.record)
        self.assertTrue(movement.order_number.startswith(superadmin_waiver.ORDER_PREFIX))
        self.assertEqual(movement.order_date, timezone.localdate())
        self.assertTrue(movement.reason.startswith(superadmin_waiver.NOTE_PREFIX))
        self.assertIn("Elvin Sahib", movement.reason)
        entry = AuditLog.objects.get(resource_type="accounts.people.movement")
        self.assertTrue(entry.changes[superadmin_waiver.AUDIT_FLAG])
        self.assertIn(superadmin_waiver.NOTE_PREFIX, entry.reason)

    def test_superadmin_expels_without_order(self):
        response = self._admin_client().post(
            reverse("accounts:student_registry_action"),
            self._movement_payload(kind="expulsion", target_group="", order_number="", order_date="", reason=""),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "expelled")

    def test_superadmin_given_order_is_kept(self):
        response = self._admin_client().post(reverse("accounts:student_registry_action"), self._movement_payload())
        self.assertEqual(response.status_code, 200, response.content)
        movement = StudentMovement.objects.get(record=self.record)
        self.assertEqual(movement.order_number, "R-140")
        self.assertNotIn(superadmin_waiver.NOTE_PREFIX, movement.reason)
        entry = AuditLog.objects.get(resource_type="accounts.people.movement")
        self.assertFalse(entry.changes[superadmin_waiver.AUDIT_FLAG])

    def test_regular_role_still_needs_order_number_and_date(self):
        response = self._post_movement(order_number="", reason="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "order_number_required")
        response = self._post_movement(order_date="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "order_date_required")
        self.assertFalse(StudentMovement.objects.exists())

    def test_dialog_marks_order_optional_only_for_superadmin(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "student-registry"})
        admin_html = self._admin_client().get(url).json()["html"]
        staff_html = self._client("student_services").get(url).json()["html"]
        self.assertIn('name="order_number"', admin_html)
        self.assertIn("data-superadmin-waiver-hint", admin_html)
        self.assertNotIn('name="order_number" maxlength="64" required', admin_html)
        self.assertIn('name="order_number" maxlength="64" required data-ems-required', staff_html)
        self.assertNotIn("data-superadmin-waiver-hint", staff_html)


class ContextProcessorTest(TestCase):
    def _context(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return view_as_context(request)

    def test_flag_follows_request_user(self):
        admin = User.objects.create_user("cp_sa_admin", "cp_sa_admin@qku.edu.az", "pw", is_superuser=True)
        plain = User.objects.create_user("cp_sa_plain", "cp_sa_plain@qku.edu.az", "pw")
        self.assertTrue(self._context(admin)["superadmin_doc_waiver"])
        self.assertFalse(self._context(plain)["superadmin_doc_waiver"])
