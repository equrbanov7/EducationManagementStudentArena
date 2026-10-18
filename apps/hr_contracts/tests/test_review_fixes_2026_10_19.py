"""Müstəqil rəyin düzəlişləri (2026-10-19) — hər tapıntı üçün test (A1–A7 + kiçik qeydlər).

A1 təsdiqdən sonra redaktə · A2 qaralamanın işçiyə sızması / «Qaralamanı ləğv et» · A3 UNIT menecerin əhatəsi ·
A4 müddət uzadılanda xatırlatma · A5 yetim fayllar · A6 RLS altında alıcılar · A7 silmə ↔ append-only trigger.
"""

from __future__ import annotations

import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.hr_contracts.constants import ContractStatus, EventKind
from apps.hr_contracts.media import check_file_access
from apps.hr_contracts.models import EmploymentContract, EmploymentContractEvent
from apps.hr_contracts.services import contracts as service
from apps.hr_contracts.services import reminders
from apps.hr_contracts.services.errors import ContractError
from apps.hr_contracts.services.queries import employee_contracts
from apps.notifications.models import InAppNotification
from core.rls import bypass_rls

from .world import PDF_BYTES, actor, build_world, client_for, contract_data, days, make_contract

_MEDIA = tempfile.mkdtemp(prefix="hrc-review-")


def _pdf(name="m.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


def _kinds(contract):
    with bypass_rls():
        return list(contract.events.order_by("created_at").values_list("kind", flat=True))


def _edit(world, contract, **overrides):
    data = contract_data(world["t1"], number=contract.number, id=contract.pk, unit=contract.unit_id, **overrides)
    return client_for(world["org"], world["hr"]).post(reverse("hr_contracts:save"), data)


@override_settings(MEDIA_ROOT=_MEDIA)
class ReviewFixesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcreview")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    # ── A1 ────────────────────────────────────────────────────────────────
    def test_a1_acknowledged_contract_terms_are_locked(self):
        contract = make_contract(self.w, number="A1-1", staff_rate="1")
        with bypass_rls():
            service.mark_sent(actor(self.w, "hr"), contract.pk)
            service.acknowledge(self.w["t1"], self.w["org"], contract.pk)
        response = _edit(self.w, contract, staff_rate="0.25")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "acknowledged_locked")
        self.assertIn("«Yenilə»", response.json()["message"])
        upload = client_for(self.w["org"], self.w["hr"]).post(
            reverse("hr_contracts:save"),
            {**contract_data(self.w["t1"], number="A1-1", id=contract.pk, unit=contract.unit_id, staff_rate="1"),
             "file": _pdf()},
        )  # fmt: skip
        self.assertEqual(upload.status_code, 409)
        notes_only = _edit(self.w, contract, staff_rate="1", notes="Daxili qeyd")
        self.assertEqual(notes_only.status_code, 200, notes_only.content)
        with bypass_rls():
            contract.refresh_from_db()
        self.assertEqual(str(contract.staff_rate), "1.00")
        self.assertEqual(contract.notes, "Daxili qeyd")
        self.assertIsNotNone(contract.acknowledged_at)

    def test_a1_edit_after_send_requires_resend(self):
        contract = make_contract(self.w, number="A1-2")
        with bypass_rls():
            service.mark_sent(actor(self.w, "hr"), contract.pk)
        self.assertEqual(_edit(self.w, contract, notes="yalnız qeyd").status_code, 200)
        with bypass_rls():
            contract.refresh_from_db()
        self.assertIsNotNone(contract.sent_at)  # daxili qeyd yenidən göndərmə tələb etmir
        self.assertEqual(_edit(self.w, contract, position="Dosent").status_code, 200)
        with bypass_rls():
            contract.refresh_from_db()
        self.assertIsNone(contract.sent_at)
        self.assertEqual(_kinds(contract)[-1], EventKind.RESEND_REQUIRED)
        with self.assertRaises(ContractError) as caught, bypass_rls():
            service.acknowledge(self.w["t1"], self.w["org"], contract.pk)
        self.assertEqual(caught.exception.status, 404)  # köhnə mətni təsdiqləmək mümkün deyil
        with bypass_rls():
            service.mark_sent(actor(self.w, "hr"), contract.pk)
            service.acknowledge(self.w["t1"], self.w["org"], contract.pk)

    # ── A2 ────────────────────────────────────────────────────────────────
    def test_a2_drafts_cannot_be_terminated_or_renewed(self):
        draft = make_contract(self.w, "t2", number="A2-1", status="draft", files={"file": _pdf()})
        with self.assertRaises(ContractError) as caught, bypass_rls():
            service.terminate(actor(self.w, "hr"), draft.pk, reason="Qaralama səhv yaradılıb")
        self.assertEqual(caught.exception.code, "draft")
        renew = contract_data(self.w["t2"], number="A2-2", start_date=days(70), end_date=days(400), renew_of=draft.pk)
        response = client_for(self.w["org"], self.w["hr"]).post(reverse("hr_contracts:save"), renew)
        self.assertEqual(response.json()["error"], "not_renewable")
        with bypass_rls():
            self.assertFalse(employee_contracts(self.w["t2"], self.w["org"]).filter(pk=draft.pk).exists())
            self.assertFalse(check_file_access(self.w["t2"], draft.file.name))

    def test_a2_discard_draft_stays_invisible_and_frees_number(self):
        draft = make_contract(self.w, "t2", number="A2-3", status="draft", files={"file": _pdf()})
        client = client_for(self.w["org"], self.w["hr"])
        response = client.post(reverse("hr_contracts:discard", args=[draft.pk]), {"note": "Səhv qeyd"})
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            draft.refresh_from_db()
            self.assertEqual(draft.status, ContractStatus.DISCARDED)
            self.assertFalse(employee_contracts(self.w["t2"], self.w["org"]).filter(pk=draft.pk).exists())
            self.assertFalse(check_file_access(self.w["t2"], draft.file.name))
            self.assertTrue(check_file_access(self.w["hr"], draft.file.name))
        self.assertEqual(_kinds(draft)[-1], EventKind.DISCARDED)
        reuse = client.post(reverse("hr_contracts:save"), contract_data(self.w["t2"], number="A2-3"))
        self.assertEqual(reuse.status_code, 200, reuse.content)
        listing = client.get("/accounts/profile/?section=hr-contracts&hrc_q=A2-3").content.decode()
        self.assertNotIn(str(draft.pk), listing)  # ləğv edilmiş qaralama defolt siyahıda yoxdur
        filtered = client.get("/accounts/profile/?section=hr-contracts&hrc_status=discarded").content.decode()
        self.assertIn(str(draft.pk), filtered)
        active = make_contract(self.w, "t1", number="A2-4")
        self.assertEqual(client.post(reverse("hr_contracts:discard", args=[active.pk])).status_code, 409)
        for name in ("send", "terminate"):
            self.assertEqual(
                client.post(reverse(f"hr_contracts:{name}", args=[draft.pk]), {"reason": "x" * 30}).status_code, 409
            )

    # ── A3 ────────────────────────────────────────────────────────────────
    def test_a3_unit_manager_cannot_reach_out_of_scope_staff(self):
        data = contract_data(self.w["m1"], number="A3-1", unit=self.w["chair_a"].pk)
        with self.assertRaises(ContractError) as caught, bypass_rls():
            service.save_contract(actor(self.w, "unit_hr"), data, {})
        self.assertEqual((caught.exception.code, caught.exception.status), ("employee_out_of_scope", 404))
        ok = contract_data(self.w["t2"], number="A3-2")
        with bypass_rls():
            contract, _created = service.save_contract(actor(self.w, "unit_hr"), ok, {})
        self.assertEqual(contract.unit, self.w["chair_a"])

    # ── A4 ────────────────────────────────────────────────────────────────
    def test_a4_extended_end_date_gets_fresh_reminders(self):
        contract = make_contract(self.w, number="A4-1", end_date=days(25))
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            self.assertEqual(reminders.run()["reminders"], 1)
        self.assertEqual(_edit(self.w, contract, end_date=days(400)).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            summary = reminders.run(on=days(375))  # yeni tarixə 25 gün qalıb
        self.assertEqual(summary["reminders"], 1)
        with bypass_rls():
            ends = sorted(
                EmploymentContractEvent.objects.filter(contract=contract, kind=EventKind.REMINDER_SENT).values_list(
                    "end_date", flat=True
                )
            )
        self.assertEqual(ends, [days(25), days(400)])
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            self.assertEqual(reminders.run(on=days(375))["reminders"], 0)  # eyni tarix üçün təkrar yoxdur

    def test_a4_expired_notice_is_per_end_date(self):
        contract = make_contract(self.w, number="A4-2", start_date=days(-300), end_date=days(-2))
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            self.assertEqual(reminders.run()["expired"], 1)
            self.assertEqual(reminders.run()["expired"], 0)
        with bypass_rls():
            EmploymentContract.objects.filter(pk=contract.pk).update(end_date=days(-1))
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            self.assertEqual(reminders.run()["expired"], 1)

    # ── A5 ────────────────────────────────────────────────────────────────
    def test_a5_replaced_file_deleted_after_commit(self):
        contract = make_contract(self.w, number="A5-1", files={"file": _pdf()})
        old = contract.file.name
        with self.captureOnCommitCallbacks(execute=True):
            response = client_for(self.w["org"], self.w["hr"]).post(
                reverse("hr_contracts:save"),
                {**contract_data(self.w["t1"], number="A5-1", id=contract.pk, unit=contract.unit_id), "file": _pdf()},
            )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            contract.refresh_from_db()
        self.assertNotEqual(contract.file.name, old)
        self.assertFalse(default_storage.exists(old))
        self.assertTrue(default_storage.exists(contract.file.name))

    def test_a5_new_file_removed_when_service_fails(self):
        stored = []
        original_track = service.track

        def spy(field_file):
            stored.append(field_file.name)
            original_track(field_file)

        data = contract_data(self.w["t1"], number="A5-2")
        with (
            mock.patch.object(service, "track", side_effect=spy),
            mock.patch.object(service, "_audit", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
            bypass_rls(),
        ):
            service.save_contract(actor(self.w, "hr"), data, {"file": _pdf()})
        self.assertEqual(len(stored), 1)
        self.assertFalse(default_storage.exists(stored[0]))

    # ── A6 ────────────────────────────────────────────────────────────────
    def test_a6_recipients_resolved_before_commit_under_transaction_scoped_rls(self):
        """Callback-lər tenant konteksti SIFIRLANMIŞ RLS rolu altında işləyir (commit-dən sonrakı vəziyyət)."""
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL RLS")
        contract = make_contract(self.w, number="A6-1", end_date=days(5))
        with self.captureOnCommitCallbacks(execute=False) as callbacks, bypass_rls():
            self.assertEqual(reminders.run()["reminders"], 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.bypass_rls', 'off', false), set_config('app.current_org_id', '', false)"
            )
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            with mock.patch("core.email_tasks.send_template_email_async.delay"):
                for callback in callbacks:
                    callback()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        with bypass_rls():
            recipients = set(
                InAppNotification.objects.filter(metadata__hr_contract_id=str(contract.pk)).values_list(
                    "recipient_id", flat=True
                )
            )
        self.assertIn(self.w["hr"].pk, recipients)
        self.assertIn(self.w["unit_hr"].pk, recipients)

    # ── A7 ────────────────────────────────────────────────────────────────
    def test_a7_user_hard_delete_nulls_actor_and_keeps_name(self):
        hr2 = get_user_model().objects.create_user(
            "hrcreview_hr2", "hr2@qku.edu.az", "pw", first_name="Leyla", last_name="Q"
        )
        from apps.organizations.models import Membership

        with bypass_rls():
            Membership.objects.create(
                user=hr2, organization=self.w["org"], role=self.w["org"].roles.get(name="hr"), is_active=True
            )
        contract = make_contract(self.w, number="A7-1", by="hr")
        from apps.hr_contracts.services.access import actor_for

        with bypass_rls():
            service.mark_sent(actor_for(hr2, self.w["org"]), contract.pk)
            hr2.delete()
            event = EmploymentContractEvent.objects.get(contract=contract, kind=EventKind.SENT)
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.actor_name, "Leyla Q")
        with self.assertRaises(IntegrityError), bypass_rls(), transaction.atomic():
            EmploymentContractEvent.objects.filter(pk=event.pk).update(note="dəyişdirildi")

    def test_a7_organization_delete_is_protected(self):
        make_contract(self.w, number="A7-2")
        with self.assertRaises(models.ProtectedError), bypass_rls(), transaction.atomic():
            self.w["org"].delete()

    # ── Kiçik qeydlər ─────────────────────────────────────────────────────
    def test_save_maps_only_number_uniqueness_to_number_taken(self):
        first = make_contract(self.w, number="N-1")
        duplicate = EmploymentContract(
            organization=self.w["org"], employee=self.w["t2"], number="N-1", start_date=days(-5), end_date=days(5)
        )
        with self.assertRaises(ContractError) as caught, bypass_rls():
            service._save(duplicate)
        self.assertEqual(caught.exception.code, "number_taken")
        first.renewed_by_id = first.pk  # hrc_not_renewed_by_self
        with self.assertRaises(ContractError) as caught, bypass_rls():
            service._save(first)
        self.assertEqual((caught.exception.code, caught.exception.status), ("conflict", 409))
