"""Zal monitoru modalı — imtahan mərkəzinin PIN göstər / yeni PIN / «başqa kompüterdə davam et» (sahib 2026-10-26).

* icazə: müəllim / nəzarətçi 403, başqa təşkilatın mərkəzi 404, mərkəz rəhbəri + işçisi 200;
* göstərmə: cari fərdi PIN JSON-da, audit-də yox; GET 405;
* yeni PIN: köhnə PIN etibarsız, yalnız başlamamış tələbəyə; audit;
* davam edən cəhd: cihaz dəyişikliyi təsdiqi (mövcud ``device_binding``) — yeni PIN yox;
* snapshot ``pin_actions`` + modal markup yalnız mərkəzdə;
* qrupu dəyişmiş tələbənin imtahanı gedirsə tam PIN sinxronu onun PIN-ini silmir;
* alt qrupa köçürmə ana qrupun imtahanlarını da sinxronlaşdırır.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import ExamStudentPin, FinalAttemptDevice
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room
from apps.exams.services.final_center.device_binding import device_change_approval_open
from apps.exams.services.student_pins import provision_exam_student_pins, student_visible_pin, verify_student_pin
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MonitorPinTests(_FlowBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = User.objects.create_user("mpin_staff", "mpin_staff@test.az", PASSWORD)
        _assign_user_to_org(cls.staff, cls.org, ProfileRole.MEMBER, "exam_center_staff")
        other_owner = User.objects.create_user("mpin_other_owner", "mpin_oo@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="MPIN Other Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=other_owner,
            status="active",
            is_active=True,
        )
        cls.other_center = User.objects.create_user("mpin_other_center", "mpin_oc@test.az", PASSWORD)
        _assign_user_to_org(cls.other_center, cls.other_org, ProfileRole.MEMBER, "exam_center_head")
        cls.exam.allowed_users.add(cls.student)

    def _client_for_org(self, user, org):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        return client

    def _url(self, name):
        return reverse(name, args=[self.session.pk, self.ticket.pk])

    def _post(self, user, name, org=None):
        client = self._client_for_org(user, org or self.org)
        return client.post(self._url(name), HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def _start_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        self.ticket.refresh_from_db()
        return attempt

    # ── İcazə ──────────────────────────────────────────────────────────────
    def test_teacher_and_invigilator_are_forbidden(self):
        for user in (self.teacher, self.invigilator):
            for name in (
                "exams:exam_center_ticket_pin_reveal",
                "exams:exam_center_ticket_pin_reissue",
                "exams:exam_center_ticket_device_release",
            ):
                with self.subTest(user=user.username, name=name):
                    self.assertEqual(self._post(user, name).status_code, 403)

    def test_other_org_center_gets_404(self):
        response = self._post(self.other_center, "exams:exam_center_ticket_pin_reveal", org=self.other_org)
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        client = self._client_for(self.center)
        self.assertEqual(client.get(self._url("exams:exam_center_ticket_pin_reveal")).status_code, 405)

    # ── PIN göstər ─────────────────────────────────────────────────────────
    def test_reveal_returns_current_pin_and_audits_without_pin(self):
        for user in (self.center, self.staff):
            with self.subTest(user=user.username):
                response = self._post(user, "exams:exam_center_ticket_pin_reveal")
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["Cache-Control"])
                data = response.json()
                self.assertTrue(data["success"])
                pin = data["pin"]
                self.assertEqual(pin, student_visible_pin(self.exam, self.student))
                self.assertEqual(data["warning"], "")
                audit = AuditLog.objects.filter(reason="final_center_monitor_pin_revealed", user=user).get()
                self.assertEqual(audit.changes["student_id"], self.student.pk)
                self.assertEqual(audit.changes["exam_id"], self.exam.pk)
                self.assertNotIn(pin, str(audit.changes) + audit.reason + audit.resource_repr)

    def test_reveal_warns_when_student_no_longer_assigned(self):
        self.exam.allowed_users.remove(self.student)
        try:
            data = self._post(self.center, "exams:exam_center_ticket_pin_reveal").json()
        finally:
            self.exam.allowed_users.add(self.student)
        self.assertTrue(data["success"])
        self.assertTrue(data["warning"])

    # ── Yeni PIN ───────────────────────────────────────────────────────────
    def test_reissue_invalidates_old_pin_and_audits(self):
        old_pin = self._post(self.center, "exams:exam_center_ticket_pin_reveal").json()["pin"]
        response = self._post(self.staff, "exams:exam_center_ticket_pin_reissue")
        self.assertEqual(response.status_code, 200)
        new_pin = response.json()["pin"]
        self.assertTrue(new_pin)
        self.assertNotEqual(new_pin, old_pin)
        self.assertTrue(verify_student_pin(self.exam, self.student, new_pin))
        self.assertFalse(verify_student_pin(self.exam, self.student, old_pin))
        self.assertTrue(AuditLog.objects.filter(reason="final_center_monitor_pin_reissued", user=self.staff).exists())

    def test_reissue_refused_for_student_in_exam(self):
        self._start_attempt()
        response = self._post(self.center, "exams:exam_center_ticket_pin_reissue")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])

    # ── Başqa kompüterdə davam et ──────────────────────────────────────────
    def test_device_release_opens_change_window_for_same_attempt(self):
        attempt = self._start_attempt()
        FinalAttemptDevice.objects.create(attempt=attempt, organization=self.org, token_hash="a" * 64)
        response = self._post(self.center, "exams:exam_center_ticket_device_release")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(device_change_approval_open(attempt))
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_finished)  # eyni cəhd — vaxt/cavablar toxunulmur
        self.assertTrue(
            AuditLog.objects.filter(reason="final_center_monitor_device_released", user=self.center).exists()
        )

    def test_device_release_refused_without_attempt(self):
        response = self._post(self.center, "exams:exam_center_ticket_device_release")
        self.assertEqual(response.status_code, 409)

    # ── Snapshot + modal ───────────────────────────────────────────────────
    def test_snapshot_pin_actions_only_for_center(self):
        url = reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk])
        center_actions = self._client_for(self.center).get(url).json()["pin_actions"]
        self.assertEqual(center_actions, {"reveal": True, "reissue": True, "device_release": False})
        invig_actions = self._client_for(self.invigilator).get(url).json()["pin_actions"]
        self.assertEqual(invig_actions, {"reveal": False, "reissue": False, "device_release": False})

        self._start_attempt()
        live_actions = self._client_for(self.center).get(url).json()["pin_actions"]
        self.assertEqual(live_actions, {"reveal": True, "reissue": False, "device_release": True})

    def test_room_monitor_modal_renders_pin_tools_for_center_only(self):
        room_url = reverse("exams:exam_center_room_monitor", args=[self.room.pk])
        response = self._client_for(self.center).get(room_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="fxc-pin-tools"')
        self.assertContains(response, 'data-pin-action="reissue"')
        self.assertContains(response, "snapshot_pin_actions.js")

        session_url = reverse("exams:exam_center_session_monitor", args=[self.session.pk])
        invig = self._client_for(self.invigilator).get(session_url)
        self.assertEqual(invig.status_code, 200)
        self.assertNotContains(invig, 'id="fxc-pin-tools"')


class ProvisionKeepsMidExamPinTests(_FlowBase):
    """Qrupu dəyişmiş (təyinatı itmiş) tələbənin imtahanı gedirsə tam sinx PIN-ini silmir."""

    def test_unassigned_student_mid_exam_keeps_pin(self):
        self.exam.allowed_users.add(self.student, self.student2)
        provision_exam_student_pins(self.exam)
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)
        # Hər iki tələbə «köçürülür» (təyinat itir); yalnız imtahanı gedən tələbənin PIN-i qalır.
        self.exam.allowed_users.remove(self.student, self.student2)

        provision_exam_student_pins(self.exam)

        self.assertTrue(ExamStudentPin.objects.filter(exam=self.exam, student=self.student).exists())
        self.assertFalse(ExamStudentPin.objects.filter(exam=self.exam, student=self.student2).exists())


class TransferSyncsParentGroupExamsTests(TestCase):
    """Alt qrupa köçürmə ana qrupa təyin olunmuş imtahanların PIN-lərini də sinxronlaşdırır (commit-dən sonra)."""

    def _run(self, **patch_kwargs):
        from apps.exams.services import unit_pin_sync

        record = SimpleNamespace(organization=object(), group_id=901)
        with (
            mock.patch("apps.registrar.subgroup_rollup.parent_group_candidates", **patch_kwargs),
            mock.patch.object(unit_pin_sync, "sync_student_pins_for_unit") as sync,
            self.captureOnCommitCallbacks(execute=True),
        ):
            unit_pin_sync._on_student_group_changed(sender=None, record=record, new_group=SimpleNamespace(pk=901))
        return [call.args[0] for call in sync.call_args_list]

    def test_subgroup_transfer_also_syncs_parent_group(self):
        self.assertEqual(self._run(return_value=[SimpleNamespace(pk=900)]), [901, 900])

    def test_parent_lookup_failure_still_syncs_new_group(self):
        self.assertEqual(self._run(side_effect=RuntimeError("boom")), [901])
