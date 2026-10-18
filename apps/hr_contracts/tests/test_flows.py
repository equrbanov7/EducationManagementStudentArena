"""Əmək müqaviləsi axınları — əlavə, redaktə (+ fərq), yeniləmə, «göndərildi», xitam, işçinin təsdiqi;
icazə (403) / əhatə (404) / view-as / tenant sərhədi; HTTP uc nöqtələri."""

from __future__ import annotations

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.hr_contracts.constants import ContractStatus, EventKind
from apps.hr_contracts.models import EmploymentContract, EmploymentContractEvent
from apps.hr_contracts.services import contracts as service
from apps.hr_contracts.services.errors import ContractError
from apps.notifications.models import InAppNotification
from core.rls import bypass_rls

from .world import Req, actor, build_world, client_for, contract_data, days, make_contract


def _kinds(contract):
    with bypass_rls():
        return list(
            EmploymentContractEvent.objects.filter(contract=contract)
            .order_by("created_at")
            .values_list("kind", flat=True)
        )


class CreateAndScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcflow")
        cls.other = build_world("hrcother")

    def _post(self, user, url, data, org=None):
        return client_for(org or self.w["org"], user).post(url, data)

    def test_hr_creates_contract_for_teacher_and_admin_staff(self):
        for key, number in (("t1", "T-1"), ("m1", "M-1")):
            response = self._post(self.w["hr"], reverse("hr_contracts:save"), contract_data(self.w[key], number=number))
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.json()["created"])
        with bypass_rls():
            teacher = EmploymentContract.objects.get(number="T-1")
            staff = EmploymentContract.objects.get(number="M-1")
        self.assertEqual(teacher.unit, self.w["chair_a"])  # əsas üzvlüyün bölməsi ön-dolduruldu
        self.assertEqual(staff.unit, self.w["office_b"])
        self.assertEqual(teacher.status, ContractStatus.ACTIVE)
        self.assertEqual(_kinds(teacher), [EventKind.CREATED])
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(resource_type=service.AUDIT_RESOURCE, resource_id=str(teacher.pk)).exists()
            )

    def test_student_cannot_get_a_contract(self):
        response = self._post(self.w["hr"], reverse("hr_contracts:save"), contract_data(self.w["s1"], number="S-1"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "employee_invalid")

    def test_other_org_employee_rejected(self):
        response = self._post(self.w["hr"], reverse("hr_contracts:save"), contract_data(self.other["t1"], number="X-1"))
        self.assertEqual(response.json()["error"], "employee_invalid")

    def test_missing_key_is_403(self):
        for key in ("t1", "dean", "s1", "trustee"):
            response = self._post(
                self.w[key], reverse("hr_contracts:save"), contract_data(self.w["t2"], number=f"N-{key}")
            )
            self.assertEqual(response.status_code, 403, key)
        with bypass_rls():
            self.assertFalse(EmploymentContract.objects.filter(number__startswith="N-").exists())

    def test_validation_messages(self):
        bad = contract_data(self.w["t1"], number="V-1", end_date=days(-400))
        self.assertEqual(
            self._post(self.w["hr"], reverse("hr_contracts:save"), bad).json()["error"], "end_before_start"
        )
        no_end = contract_data(self.w["t1"], number="V-2", end_date="")
        self.assertEqual(self._post(self.w["hr"], reverse("hr_contracts:save"), no_end).json()["field"], "end_date")
        indefinite = contract_data(self.w["t1"], number="V-3", contract_type="indefinite")
        self.assertEqual(self._post(self.w["hr"], reverse("hr_contracts:save"), indefinite).status_code, 200)
        with bypass_rls():
            self.assertIsNone(EmploymentContract.objects.get(number="V-3").end_date)
        make_contract(self.w, number="DUP-1")
        dup = contract_data(self.w["t2"], number="dup-1")
        self.assertEqual(self._post(self.w["hr"], reverse("hr_contracts:save"), dup).json()["error"], "number_taken")

    def test_unit_scoped_manager_only_inside_own_faculty(self):
        ok = self._post(self.w["unit_hr"], reverse("hr_contracts:save"), contract_data(self.w["t1"], number="U-1"))
        self.assertEqual(ok.status_code, 200, ok.content)
        # Rəy A3: m1 F2-dədir — F1 kadr işçisi ona müqavilə bağlaya bilməz (bölmə hansı seçilsə də), 404.
        for index, unit in enumerate(("", self.w["office_b"].pk, self.w["chair_a"].pk)):
            data = contract_data(self.w["m1"], number=f"U-2-{index}", unit=unit)
            outside = self._post(self.w["unit_hr"], reverse("hr_contracts:save"), data)
            self.assertEqual(outside.status_code, 404, unit)
            self.assertEqual(outside.json()["error"], "employee_out_of_scope")
        forced = contract_data(self.w["t2"], number="U-3", unit=self.w["office_b"].pk)  # əhatədəki işçi, kənar bölmə
        self.assertEqual(
            self._post(self.w["unit_hr"], reverse("hr_contracts:save"), forced).json()["error"], "unit_out_of_scope"
        )
        with bypass_rls():
            self.assertFalse(EmploymentContract.objects.filter(number__startswith="U-2").exists())
        staff_contract = make_contract(self.w, "m1", number="M-OUT")
        response = self._post(self.w["unit_hr"], reverse("hr_contracts:send", args=[staff_contract.pk]), {})
        self.assertEqual(response.status_code, 404)

    def test_other_tenant_contract_is_404(self):
        foreign = make_contract(self.other, number="OTHER-1")
        for name in ("send", "terminate", "history"):
            client = client_for(self.w["org"], self.w["hr"])
            url = reverse(f"hr_contracts:{name}", args=[foreign.pk])
            response = client.get(url) if name == "history" else client.post(url, {"reason": "x" * 30})
            self.assertEqual(response.status_code, 404, name)


class LifecycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrclife")

    def setUp(self):
        self.contract = make_contract(self.w, number="L-1")

    def test_edit_records_diff(self):
        data = contract_data(self.w["t1"], number="L-1", position="Dosent", id=self.contract.pk)
        response = client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:save"), data)
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            event = EmploymentContractEvent.objects.get(contract=self.contract, kind=EventKind.EDITED)
        self.assertEqual(event.data["changes"]["position"], ["Baş müəllim", "Dosent"])

    def test_renew_links_chain_and_closes_old(self):
        data = contract_data(
            self.w["t1"], number="L-2", start_date=days(66), end_date=days(431), renew_of=self.contract.pk
        )
        data.pop("employee")
        response = client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:save"), data)
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.contract.refresh_from_db()
            new = EmploymentContract.objects.get(number="L-2")
        self.assertEqual(self.contract.status, ContractStatus.RENEWED)
        self.assertEqual(self.contract.renewed_by, new)
        self.assertEqual(new.employee, self.w["t1"])
        self.assertIn(EventKind.RENEWED, _kinds(self.contract))
        again = client_for(self.w["org"], self.w["hr"]).post(
            reverse("hr_contracts:save"), {**data, "number": "L-3", "start_date": days(500).isoformat(), "end_date": ""}
        )
        self.assertEqual(again.json()["error"], "not_renewable")

    def test_renew_must_start_after_previous(self):
        data = contract_data(self.w["t1"], number="L-4", start_date=days(-400), renew_of=self.contract.pk)
        response = client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:save"), data)
        self.assertEqual(response.json()["error"], "start_before_previous")

    def test_terminate_requires_reason(self):
        client = client_for(self.w["org"], self.w["hr"])
        url = reverse("hr_contracts:terminate", args=[self.contract.pk])
        self.assertEqual(client.post(url, {"reason": "qısa"}).json()["error"], "reason_required")
        response = client.post(url, {"reason": "Öz ərizəsi ilə xitam verilir", "terminated_at": days(-1).isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, ContractStatus.TERMINATED)
        self.assertEqual(client.post(url, {"reason": "Təkrar xitam cəhdi yazılır"}).status_code, 409)
        edit = contract_data(self.w["t1"], number="L-1", id=self.contract.pk)
        self.assertEqual(client.post(reverse("hr_contracts:save"), edit).json()["error"], "closed")

    def test_send_notifies_employee_and_acknowledge_notifies_sender(self):
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = client_for(self.w["org"], self.w["hr"]).post(
                reverse("hr_contracts:send", args=[self.contract.pk]), {"note": "Müqavilə 1 noyabrdan qüvvəyə minir."}
            )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            note = InAppNotification.objects.get(recipient=self.w["t1"], metadata__kind="sent")
        self.assertIn("e-poçtunuza göndərilib", note.message)
        self.assertIn("tanış olduğunuzu təsdiqləyin", note.message)
        # Sahib 2026-10-19: imzalı nüsxə / HR-a təhvil addımı YOXDUR — sistemdəki təsdiq son addımdır.
        for text in [note.message, *(message.body for message in mail.outbox)]:
            self.assertNotIn("imza", text.lower())
            self.assertNotIn("nüsxə", text.lower())
        self.assertIn("my-contracts", note.link)
        self.assertTrue(any(self.w["t1"].email in message.to for message in mail.outbox))

        other = client_for(self.w["org"], self.w["t2"]).post(
            reverse("hr_contracts:acknowledge", args=[self.contract.pk])
        )
        self.assertEqual(other.status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            response = client_for(self.w["org"], self.w["t1"]).post(
                reverse("hr_contracts:acknowledge", args=[self.contract.pk]), {"note": "Tanış oldum"}
            )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.contract.refresh_from_db()
            self.assertTrue(
                InAppNotification.objects.filter(recipient=self.w["hr"], metadata__kind="acknowledged").exists()
            )
        self.assertIsNotNone(self.contract.acknowledged_at)
        self.assertEqual(
            client_for(self.w["org"], self.w["t1"])
            .post(reverse("hr_contracts:acknowledge", args=[self.contract.pk]))
            .status_code,
            409,
        )
        resend = client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:send", args=[self.contract.pk]))
        self.assertEqual(resend.json()["error"], "already_acknowledged")

    def test_acknowledge_without_send_is_404(self):
        response = client_for(self.w["org"], self.w["t1"]).post(
            reverse("hr_contracts:acknowledge", args=[self.contract.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_view_as_never_writes(self):
        view_as = actor(self.w, "hr", view_as=True)
        self.assertFalse(view_as.can_manage)
        self.assertTrue(view_as.can_view)
        with self.assertRaises(ContractError) as caught:
            service.mark_sent(view_as, self.contract.pk)
        self.assertEqual(caught.exception.status, 403)
        with bypass_rls():
            service.mark_sent(actor(self.w, "hr"), self.contract.pk)
        with self.assertRaises(ContractError):
            service.acknowledge(
                self.w["t1"], self.w["org"], self.contract.pk, request=Req(self.w["t1"], self.w["org"], view_as=True)
            )

    def test_draft_hidden_from_employee_until_sent(self):
        from apps.hr_contracts.services.queries import employee_contracts

        draft = make_contract(self.w, "t2", number="D-1", status="draft")
        with bypass_rls():
            self.assertFalse(employee_contracts(self.w["t2"], self.w["org"]).filter(pk=draft.pk).exists())
            service.mark_sent(actor(self.w, "hr"), draft.pk)  # rəy A2: göndərmə qaralamanı əvvəlcə qüvvəyə mindirir
            draft.refresh_from_db()
            self.assertTrue(employee_contracts(self.w["t2"], self.w["org"]).filter(pk=draft.pk).exists())
        self.assertEqual(draft.status, ContractStatus.ACTIVE)
        self.assertEqual(_kinds(draft)[-2:], [EventKind.ACTIVATED, EventKind.SENT])
        other = make_contract(self.w, "t2", number="D-2", status="draft")
        data = contract_data(self.w["t2"], number="D-2", id=other.pk, status="active")
        client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:save"), data)
        with bypass_rls():
            other.refresh_from_db()
        self.assertEqual(other.status, ContractStatus.ACTIVE)
        self.assertIn(EventKind.ACTIVATED, _kinds(other))
