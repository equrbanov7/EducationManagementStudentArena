"""Gündəlik bitmə xatırlatmaları — hədd seçimi, idempotentlik, yenilənmiş / xitam verilmiş müqavilə, alıcıların
əhatəsi, «müddəti bitdi», quru icra, management komandası, runtime tənzimləməsi."""

from __future__ import annotations

from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.runtime_settings_models import RuntimeSetting
from apps.hr_contracts.constants import EventKind
from apps.hr_contracts.models import EmploymentContractEvent
from apps.hr_contracts.services import contracts as service
from apps.hr_contracts.services.reminders import current_threshold, run
from apps.notifications.models import InAppNotification
from core import runtime_settings
from core.rls import bypass_rls

from .world import actor, build_world, days, make_contract


def _recipients(contract, kind="reminder"):
    with bypass_rls():
        return set(
            InAppNotification.objects.filter(
                metadata__hr_contract_id=str(contract.pk), metadata__kind=kind
            ).values_list("recipient_id", flat=True)
        )


class ThresholdTest(TestCase):
    def test_current_threshold_picks_smallest_reached(self):
        thresholds = [60, 30, 14, 7, 1]
        self.assertIsNone(current_threshold(61, thresholds))
        self.assertEqual(current_threshold(60, thresholds), 60)
        self.assertEqual(current_threshold(45, thresholds), 60)
        self.assertEqual(current_threshold(10, thresholds), 14)
        self.assertEqual(current_threshold(0, thresholds), 1)


class ReminderRunTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcrem")

    def _run(self, **kwargs):
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            return run(**kwargs)

    def test_once_per_threshold_and_scoped_recipients(self):
        teacher = make_contract(self.w, "t1", number="R-1", end_date=days(25))  # F1 / Kafedra A → 30 günlük hədd
        staff = make_contract(self.w, "m1", number="R-2", end_date=days(5))  # F2 / Şöbə B → 7 günlük hədd
        far = make_contract(self.w, "t2", number="R-3", end_date=days(200))
        mail.outbox.clear()
        summary = self._run()
        self.assertEqual(summary["reminders"], 2)
        self.assertEqual(
            _recipients(teacher), {self.w["t1"].pk, self.w["hr"].pk, self.w["unit_hr"].pk}
        )  # HR (org) + F1 kadr işçisi; rektor (`*`) spam almır
        self.assertEqual(_recipients(staff), {self.w["m1"].pk, self.w["hr"].pk})  # F1 kadr işçisi F2-ni görmür
        self.assertEqual(_recipients(far), set())
        self.assertTrue(any(self.w["t1"].email in message.to for message in mail.outbox))
        with bypass_rls():
            event = EmploymentContractEvent.objects.get(contract=teacher, kind=EventKind.REMINDER_SENT)
        self.assertEqual(event.threshold, 30)

        again = self._run()
        self.assertEqual(again["reminders"], 0)
        self.assertEqual(again["skipped"], 2)
        with bypass_rls():
            self.assertEqual(InAppNotification.objects.filter(metadata__kind="reminder").count(), 5)

        later = self._run(on=days(20))  # 5 gün qalıb → 7 günlük hədd yenidir
        self.assertEqual(later["reminders"], 1)
        with bypass_rls():
            self.assertEqual(
                sorted(
                    EmploymentContractEvent.objects.filter(contract=teacher)
                    .values_list("threshold", flat=True)
                    .exclude(threshold=None)
                ),
                [7, 30],
            )

    def test_renewed_and_terminated_are_skipped(self):
        renewed = make_contract(self.w, "t1", number="R-10", end_date=days(10))
        make_contract(self.w, "t1", number="R-11", start_date=days(11), end_date=days(400), renew_of=renewed.pk)
        terminated = make_contract(self.w, "t2", number="R-12", end_date=days(10))
        draft = make_contract(self.w, "m1", number="R-13", end_date=days(10), status="draft")
        with bypass_rls():
            service.terminate(actor(self.w, "hr"), terminated.pk, reason="Ərizə əsasında xitam")
        summary = self._run()
        self.assertEqual(summary["reminders"], 0)
        for contract in (renewed, terminated, draft):
            self.assertEqual(_recipients(contract), set())

    def test_expired_notice_once_and_dry_run_writes_nothing(self):
        expired = make_contract(self.w, "t1", number="R-20", start_date=days(-300), end_date=days(-2))
        dry = self._run(dry_run=True)
        self.assertEqual(dry["expired"], 1)
        with bypass_rls():
            self.assertFalse(
                EmploymentContractEvent.objects.filter(contract=expired, kind=EventKind.EXPIRED_NOTICE).exists()
            )
        self.assertEqual(_recipients(expired, "expired"), set())
        self.assertEqual(self._run()["expired"], 1)
        self.assertEqual(_recipients(expired, "expired"), {self.w["t1"].pk, self.w["hr"].pk, self.w["unit_hr"].pk})
        self.assertEqual(self._run()["expired"], 0)

    def test_old_archive_does_not_get_expired_spam(self):
        old = make_contract(self.w, "t2", number="R-21", start_date=days(-800), end_date=days(-200))
        self._run()
        self.assertEqual(_recipients(old, "expired"), set())

    def test_late_registration_gets_only_current_threshold(self):
        late = make_contract(self.w, "m1", number="R-30", end_date=days(10))
        self._run()
        with bypass_rls():
            self.assertEqual(
                list(
                    EmploymentContractEvent.objects.filter(contract=late, kind=EventKind.REMINDER_SENT).values_list(
                        "threshold", flat=True
                    )
                ),
                [14],
            )

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_runtime_setting_changes_thresholds(self):
        RuntimeSetting.objects.create(key="hr.contract_reminder_days", value="30,7,1")
        runtime_settings.invalidate()
        try:
            contract = make_contract(self.w, "t1", number="R-40", end_date=days(12))
            summary = self._run()
            self.assertEqual(summary["thresholds"], [30, 7, 1])
            with bypass_rls():
                event = EmploymentContractEvent.objects.get(contract=contract, kind=EventKind.REMINDER_SENT)
            self.assertEqual(event.threshold, 30)
        finally:
            runtime_settings.invalidate()

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_email_switch_off_keeps_in_app_only(self):
        RuntimeSetting.objects.create(key="hr.contract_email_enabled", value=False)
        runtime_settings.invalidate()
        try:
            contract = make_contract(self.w, "t1", number="R-50", end_date=days(3))
            mail.outbox.clear()
            self._run()
            self.assertIn(self.w["t1"].pk, _recipients(contract))
            self.assertEqual(mail.outbox, [])
        finally:
            runtime_settings.invalidate()

    def test_management_command_dry_run_and_apply(self):
        contract = make_contract(self.w, "t2", number="R-60", end_date=days(1))
        out = StringIO()
        call_command("send_contract_reminders", "--dry-run", "--org", self.w["org"].slug, stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertIn("R-60", out.getvalue())
        with bypass_rls():
            self.assertFalse(
                EmploymentContractEvent.objects.filter(contract=contract, kind=EventKind.REMINDER_SENT).exists()
            )
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("send_contract_reminders", stdout=out)
        self.assertIn("APPLY", out.getvalue())
        with bypass_rls():
            self.assertTrue(
                EmploymentContractEvent.objects.filter(contract=contract, kind=EventKind.REMINDER_SENT).exists()
            )

    def test_celery_task_and_beat_entry(self):
        from pathlib import Path

        from django.conf import settings

        from apps.hr_contracts.tasks import send_contract_reminders

        beat = (Path(settings.BASE_DIR) / "config/settings/components/celery_cache.py").read_text(encoding="utf-8")
        self.assertIn('"hr-contracts-send-reminders": {\n        "task": "hr_contracts.send_contract_reminders"', beat)
        make_contract(self.w, "t1", number="R-70", end_date=days(6))
        with self.captureOnCommitCallbacks(execute=True):
            summary = send_contract_reminders.apply().get()
        self.assertGreaterEqual(summary["reminders"], 1)
        self.assertNotIn("items", summary)
