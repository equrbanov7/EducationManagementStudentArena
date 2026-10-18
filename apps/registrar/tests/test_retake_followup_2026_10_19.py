"""25% müraciəti — sahibin cavabları (2026-10-19): məbləğ, cəhd sayı, pəncərə, bağlanış qərarı, mühasibat bandı."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.registrar import (
    retake_closure,
    retake_decisions,
    retake_eligibility,
    retake_rules,
    retake_services,
    retake_window,
)
from apps.registrar.models import RetakeEventAction, RetakeStatus, RetakeTuition, RetakeWindow
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf

PROFILE = "/accounts/profile/"


def _row(student, org, subject):
    rows = retake_eligibility.failed_subjects(student=student, organization=org)
    return next((r for r in rows if r["subject"].id == subject.id), None)


class _Base(RetakeBase):
    def setUp(self):
        self.fail_exam()

    def _verified(self, paid="50"):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount=paid
            )
            app.refresh_from_db()
        return app

    def _admitted(self):
        app = self._verified()
        with bypass_rls():
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            app.refresh_from_db()
        return app

    def _tuition(self, amount, program=None):
        with bypass_rls():
            return RetakeTuition.objects.create(
                organization=self.org,
                academic_year=self.past.academic_year,
                admission_year=2025,
                program=program,
                annual_amount=Decimal(amount),
            )


@override_settings(UNIVERSITY_MODE=True)
class FeeTest(_Base):
    """Sahib 1: «İlliyə görə hesablanır» — düstur konfiqurasiya olunandır, fərq xəbərdarlıqdır."""

    def test_no_tuition_row_means_ask_accounting(self):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
        self.assertIsNone(app.expected_fee)
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Məbləği Mühasibatlıqdan öyrənin", body)

    def test_formula_default_and_program_override(self):
        self._tuition("2400")  # 2400 × 25% × 5/60 = 50.00
        with bypass_rls():
            self.assertEqual(_fee(self), Decimal("50.00"))
        self._tuition("3000", program=self.program)  # ixtisasa xas sətir üstündür → 62.50
        with bypass_rls():
            self.assertEqual(_fee(self), Decimal("62.50"))
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Təxmini məbləğ: 62.5 AZN", body)

    @override_settings(RETAKE_FEE_ANNUAL_CREDITS=0, RETAKE_FEE_PERCENT=25)
    def test_zero_annual_credits_means_no_credit_division(self):
        self._tuition("2400")
        with bypass_rls():
            self.assertEqual(_fee(self), Decimal("600.00"))

    def test_verify_records_paid_and_expected_and_warns_on_mismatch(self):
        self._tuition("2400")
        app = self._verified(paid="45")
        with bypass_rls():
            event = app.events.get(action=RetakeEventAction.PAYMENT_VERIFIED)
        self.assertEqual((app.paid_amount, app.expected_fee), (Decimal("45.00"), Decimal("50.00")))
        self.assertTrue(event.metadata["amount_mismatch"])
        self.assertEqual(event.metadata["fee_inputs"]["annual_amount"], "2400.00")
        self.assertEqual(app.status, RetakeStatus.PAYMENT_VERIFIED)  # fərq blok deyil
        body = (
            self.client_for(self.accountant)
            .get(f"{PROFILE}?section=retake-desk&rt_tab=payments&rt_status=")
            .content.decode()
        )
        self.assertIn("Ödənilən məbləğ gözləniləndən fərqlidir", body)

    def test_paid_amount_is_required(self):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            with self.assertRaises(ValidationError):
                retake_decisions.verify_payment(actor=self.accountant, organization=self.org, application_id=app.id)

    def test_tuition_table_permissions(self):
        url = reverse("retake:tuition_save")
        data = {"academic_year": self.past.academic_year, "admission_year": "2025", "annual_amount": "2400"}
        self.assertEqual(self.client_for(self.dean).post(url, data).status_code, 403)
        ok = self.client_for(self.accountant).post(url, data)
        self.assertEqual(ok.status_code, 200, ok.content)
        again = self.client_for(self.accountant).post(url, {**data, "annual_amount": "2600"})  # yeniləmə
        self.assertEqual(again.status_code, 200)
        with bypass_rls():
            row = RetakeTuition.objects.get(organization=self.org)
        self.assertEqual(row.annual_amount, Decimal("2600.00"))
        body = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk&rt_tab=fees").content.decode()
        self.assertIn("Təhsil haqqı cədvəli", body)
        deleted = self.client_for(self.accountant).post(reverse("retake:tuition_delete", args=[row.pk]))
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(RetakeTuition.objects.exists())


def _fee(test):
    from apps.registrar import retake_fees

    context = retake_fees.student_context(test.student, test.org)
    return retake_fees.estimate(context=context, period=test.past, subject=test.subject)["amount"]


@override_settings(UNIVERSITY_MODE=True)
class AttemptSettingTest(_Base):
    """Sahib 2: defolt 1, «Sistem tənzimləmələri»ndə 1–10."""

    def test_setting_is_editable_and_shown(self):
        from core import runtime_settings

        spec = runtime_settings.SPECS["retake.max_attempts"]
        self.assertEqual((spec.kind, spec.min, spec.max, spec.default()), ("int", 1, 10, 1))
        with override_settings(RETAKE_MAX_ATTEMPTS=3):
            self.assertEqual(retake_rules.max_attempts(), 3)
            body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Bir fənn üzrə 25% cəhd limiti: 3", body)


@override_settings(UNIVERSITY_MODE=True)
class WindowTest(_Base):
    """Sahib 3: «İmtahan mərkəzi açsın bunu» — dövr üzrə pəncərə + ümumi açar."""

    def _center(self):
        return self._staff("rt_center_w", ["exam_center.decide"], RoleScopeType.ORGANIZATION)

    def test_closed_window_blocks_applications(self):
        with bypass_rls():
            retake_window.close_window(actor=self._center(), organization=self.org, window_id=self.window.pk)
            self.assertFalse(retake_rules.applications_open(self.org))
            self.assertFalse(_row(self.student, self.org, self.subject)["options"]["retake_25"]["allowed"])
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
                )
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Müraciət pəncərəsi bağlıdır", body)

    @override_settings(RETAKE_APPLICATIONS_OPEN=False)
    def test_master_switch_wins_over_open_window(self):
        with bypass_rls():
            self.assertIsNotNone(retake_window.current(self.org))
            self.assertFalse(retake_rules.applications_open(self.org))

    def test_exam_centre_opens_and_closes_with_history(self):
        center = self._center()
        client = self.client_for(center)
        with bypass_rls():
            retake_window.close_window(actor=center, organization=self.org, window_id=self.window.pk)
        self.assertEqual(
            self.client_for(self.dean)
            .post(reverse("retake:window_open"), {"period": str(self.current.pk)})
            .status_code,
            403,
        )
        closes = (timezone.localtime() + datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        opened = client.post(reverse("retake:window_open"), {"period": str(self.current.pk), "closes_at": closes})
        self.assertEqual(opened.status_code, 200, opened.content)
        twice = client.post(reverse("retake:window_open"), {"period": str(self.current.pk)})
        self.assertEqual(twice.status_code, 400)
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("tarixinədək", body)
        with bypass_rls():
            live = retake_window.current(self.org)
        closed = client.post(reverse("retake:window_close", args=[live.pk]))
        self.assertEqual(closed.status_code, 200)
        with bypass_rls():
            rows = RetakeWindow.objects.filter(organization=self.org)
            self.assertEqual(rows.count(), 2)
            self.assertTrue(all(w.closed_at for w in rows))
            self.assertEqual(rows.get(pk=live.pk).closed_by, center)
        section = client.get(f"{PROFILE}?section=retake-windows").content.decode()
        self.assertIn('data-profile-section-panel="retake-windows"', section)
        self.assertIn("Tarixçə", section)

    def test_scheduled_and_expired_windows(self):
        center = self._center()
        now = timezone.now()
        with bypass_rls():
            retake_window.close_window(actor=center, organization=self.org, window_id=self.window.pk)
            RetakeWindow.objects.create(
                organization=self.org,
                period=self.past,
                opens_at=now - datetime.timedelta(days=3),
                closes_at=now - datetime.timedelta(days=1),
            )
            self.assertIsNone(retake_window.current(self.org))
            future = retake_window.open_window(
                actor=center, organization=self.org, period=self.current, opens_at=now + datetime.timedelta(days=2)
            )
            self.assertIsNone(retake_window.current(self.org))
            self.assertEqual(retake_window.upcoming(self.org), future)
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("tarixində açılacaq", body)


class ClosureTest(_Base):
    """Sahib 4: qaytarılma yoxdur, amma ödənişdən sonra hər bağlanış rəsmi qərarla."""

    def test_student_cannot_withdraw_after_payment(self):
        app = self._verified()
        with bypass_rls(), self.assertRaises(ValidationError):
            retake_services.withdraw(student=self.student, organization=self.org, application_id=app.id)

    def test_no_show_needs_decision_and_consumes_attempt(self):
        app = self._admitted()
        with bypass_rls():
            with self.assertRaises(ValidationError):
                retake_closure.close(
                    actor=self.dean,
                    organization=self.org,
                    application_id=app.id,
                    action="no_show",
                    reason="Tələbə təyin olunmuş 25% imtahanına gəlmədi.",
                )
            retake_closure.close(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                action="no_show",
                reason="Tələbə təyin olunmuş 25% imtahanına gəlmədi.",
                order_number="77/D",
                order_date="2026-10-19",
            )
            app.refresh_from_db()
            event = app.events.get(action=RetakeEventAction.NO_SHOW)
            row = _row(self.student, self.org, self.subject)
        self.assertEqual(app.status, RetakeStatus.NO_SHOW)
        self.assertEqual((app.closure_order_number, str(app.closure_order_date)), ("77/D", "2026-10-19"))
        self.assertIn("Qaytarılma yoxdur", event.note)
        self.assertEqual(event.metadata["refund"], "none")
        self.assertEqual(row["attempts_used"], 1)  # «gəlmədi» cəhdi istifadə olunmuş sayılır
        self.assertFalse(row["options"]["retake_25"]["allowed"])

    def test_reject_after_payment_needs_decision_document(self):
        app = self._verified()
        reason = "Ödəniş başqa fənn üçün edilib, müraciət rədd olunur."
        with bypass_rls():
            with self.assertRaises(ValidationError):
                retake_decisions.reject(actor=self.dean, organization=self.org, application_id=app.id, reason=reason)
            retake_decisions.reject(
                actor=self.dean, organization=self.org, application_id=app.id, reason=reason, document=pdf("qerar.pdf")
            )
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.REJECTED)
        self.assertTrue(app.closure_document.name.startswith(f"retake_documents/{self.org.id}/"))

    @override_settings(UNIVERSITY_MODE=True)
    def test_staff_withdraw_over_http(self):
        app = self._admitted()
        url = reverse("retake:decision", args=[app.id])
        data = {"action": "withdraw", "reason": "Tələbənin yazılı ərizəsi ilə müraciət geri götürülür."}
        self.assertEqual(self.client_for(self.dean).post(url, data).status_code, 400)  # qərarsız
        ok = self.client_for(self.dean).post(url, {**data, "order_number": "12", "order_date": "2026-10-19"})
        self.assertEqual(ok.status_code, 200, ok.content)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.WITHDRAWN)
        self.assertEqual(self.client_for(self.accountant).post(url, data).status_code, 403)


class AccountingDeviationTest(RetakeBase):
    """Sahib 5: ±10% bandı «Sistem tənzimləmələri» → ``accounting.deviation_percent``."""

    def test_band_follows_setting(self):
        from apps.accounts.services.accounting import constants as C
        from apps.accounts.services.accounting.rows import plan_status
        from core import runtime_settings

        spec = runtime_settings.SPECS["accounting.deviation_percent"]
        self.assertEqual((spec.default(), spec.min, spec.max), (10, 0, 50))
        self.assertEqual(plan_status(100, 85), C.STATUS_UNDER)
        with override_settings(ACCOUNTING_DEVIATION_PERCENT=20):
            self.assertEqual(plan_status(100, 85), C.STATUS_ON_PLAN)
            self.assertEqual(C.deviation_percent(), 20)
