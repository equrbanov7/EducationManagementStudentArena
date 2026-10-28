"""25% — «Ödənişin qaytarılması qərarı» (sahib 2026-10-19, tövsiyə olunan variant).

Kilidlənən qaydalar:

* defolt qaytarılma YOXDUR; qərar YALNIZ ödənişi təsdiqlənmiş və sonra bağlanmış (rədd / gəlmədi / geri götürülmüş)
  25% müraciətinə, BİR DƏFƏ, əmr № + tarix və ya sənəd və ≥ 20 simvol səbəblə;
* qərar — təşkilat əhatəli ``retake.manage`` (Tədris şöbəsi / RİM); fakültə dekanı, mühasib, koordinator, tələbə — 403;
* icra — ``retake.payment_verify`` (Mühasibatlıq) «Qaytarıldı» (tarix + arayış №), bir dəfə; qərarsız olmaz;
* hər addım append-only hadisədir; DB trigger-i qərar / icra sahələrini və vəziyyətin geri dönməsini bloklayır;
* mühasib «Qaytarılacaq ödənişlər» növbəsində məbləği, əmri və tələbəni görür (bal yox); tələbə kartında vəziyyət;
* bildiriş tələbəyə və mühasibə commit-dən sonra gedir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.registrar import retake_closure, retake_decisions, retake_eligibility, retake_refund, retake_services
from apps.registrar.models import RetakeEventAction, RetakeRefundState, RetakeStatus
from apps.registrar.retake_media import check_document_access
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf

PROFILE = "/accounts/profile/"
REASON = "Tələbə xəstəlik səbəbindən imtahana gələ bilmədi, rektorun əmri ilə ödəniş qaytarılır."


def today():
    """Use the university-local day at execution, even after midnight during a long suite."""
    return timezone.localdate().isoformat()


@override_settings(UNIVERSITY_MODE=True)
class RefundTest(RetakeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            # Tədris şöbəsi / RİM — ``retake.manage`` TƏŞKİLAT əhatəsində (dekan isə fakültə əhatəsindədir).
            cls.office = cls._staff("rt_office", ["retake.manage"], RoleScopeType.ORGANIZATION)

    def setUp(self):
        self.fail_exam()

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _verified(self, paid="50", student=None):
        student = student or self.student
        enrollment = student.enrollments.get(offering__subject=self.subject)
        if student != self.student:
            self.fail_exam(enrollment=enrollment)
        with bypass_rls():
            app = retake_services.apply(
                student=student,
                organization=self.org,
                enrollment_id=enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount=paid
            )
            app.refresh_from_db()
        return app

    def _closed(self, action="no_show", paid="50"):
        app = self._verified(paid)
        with bypass_rls():
            if action == "no_show":
                retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            retake_closure.close(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                action=action,
                reason="Rəsmi qərarla müraciət bağlanır — test fiksturu.",
                order_number="77/D",
                order_date=today(),
            )
            app.refresh_from_db()
        return app

    def _decide(self, app, actor=None, **extra):
        data = {"reason": REASON, "order_number": "15/Q", "order_date": today(), **extra}
        with bypass_rls():
            retake_refund.decide(actor=actor or self.office, organization=self.org, application_id=app.id, **data)
            app.refresh_from_db()
        return app

    def _mark(self, app, actor=None, **extra):
        data = {"refunded_on": today(), "reference": "BANK-2026-001", **extra}
        with bypass_rls():
            retake_refund.mark_refunded(
                actor=actor or self.accountant, organization=self.org, application_id=app.id, **data
            )
            app.refresh_from_db()
        return app

    # ── Səlahiyyət ──────────────────────────────────────────────────────────
    def test_permission_matrix_over_http(self):
        app = self._closed()
        url = reverse("retake:refund", args=[app.id])
        decide = {"action": "decide", "reason": REASON, "order_number": "15/Q", "order_date": today()}
        for user in (self.accountant, self.dean, self.coordinator, self.student, self.teacher):
            with self.subTest(user=user.username):
                self.assertEqual(self.client_for(user).post(url, decide).status_code, 403)
        mark = {"action": "mark", "refunded_on": today(), "reference": "BANK-1"}
        self.assertEqual(self.client_for(self.accountant).post(url, mark).status_code, 400)  # qərar hələ yoxdur
        ok = self.client_for(self.office).post(url, decide)
        self.assertEqual(ok.status_code, 200, ok.content)
        for user in (self.office, self.dean, self.student):
            with self.subTest(mark=user.username):
                self.assertEqual(self.client_for(user).post(url, mark).status_code, 403)
        self.assertEqual(self.client_for(self.accountant).post(url, mark).status_code, 200)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.refund_state, RetakeRefundState.REFUNDED)
        missing = reverse("retake:refund", args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client_for(self.office).post(missing, decide).status_code, 404)

    def test_service_checks_authority_before_writing(self):
        app = self._closed()
        with bypass_rls():
            for actor in (self.dean, self.accountant):
                with self.subTest(actor=actor.username), self.assertRaises(PermissionDenied):
                    retake_refund.decide(
                        actor=actor,
                        organization=self.org,
                        application_id=app.id,
                        reason=REASON,
                        order_number="1",
                        order_date=today(),
                    )
            app.refresh_from_db()
        self.assertEqual(app.refund_state, "")
        self.assertFalse(app.events.filter(action=RetakeEventAction.REFUND_DECIDED).exists())

    def test_view_as_blocks_writes(self):
        from django.test import RequestFactory

        from apps.registrar import retake_views

        app = self._closed()
        raw = RequestFactory().post(reverse("retake:refund", args=[app.id]), {"action": "decide", "reason": REASON})
        raw.user = self.office
        raw.is_view_as = True
        self.assertEqual(retake_views.refund(raw, application_id=app.id).status_code, 403)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.refund_state, "")

    # ── Vəziyyət qaydaları ──────────────────────────────────────────────────
    def test_not_before_closure(self):
        verified = self._verified()  # ödənilib, amma bağlanmayıb
        self.assertFalse(retake_refund.is_refundable(verified))
        with bypass_rls(), self.assertRaises(ValidationError):
            retake_refund.decide(
                actor=self.office,
                organization=self.org,
                application_id=verified.id,
                reason=REASON,
                order_number="1",
                order_date=today(),
            )

    def test_withdrawn_before_payment_is_not_refundable(self):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
            retake_services.withdraw(student=self.student, organization=self.org, application_id=app.id)
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.WITHDRAWN)
        self.assertFalse(retake_refund.is_refundable(app))
        with bypass_rls(), self.assertRaises(ValidationError):
            retake_refund.decide(
                actor=self.office,
                organization=self.org,
                application_id=app.id,
                reason=REASON,
                order_number="1",
                order_date=today(),
            )

    def test_reject_after_payment_is_refundable(self):
        app = self._decide(self._closed("reject"))
        self.assertEqual((app.status, app.refund_state), (RetakeStatus.REJECTED, RetakeRefundState.DECIDED))

    def test_staff_withdraw_after_payment_is_refundable(self):
        app = self._decide(self._closed("withdraw"))
        self.assertEqual((app.status, app.refund_state), (RetakeStatus.WITHDRAWN, RetakeRefundState.DECIDED))

    def test_decision_needs_order_reason_and_valid_amount(self):
        app = self._closed()
        bad = (
            {"order_number": "", "order_date": None},  # əmr / sənəd yoxdur
            {"reason": "qısa səbəb"},
            {"amount": "60"},  # ödənilən 50-dən çox
            {"amount": "0"},
            {"amount": "abc"},
        )
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self._decide(app, **extra)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.refund_state, "")
        self._decide(app, order_number="", order_date=None, document=pdf("qaytarma.pdf"), amount="20,5")
        self.assertEqual(app.refund_amount, Decimal("20.50"))
        self.assertTrue(app.refund_document.name.startswith(f"retake_documents/{self.org.id}/"))

    def test_only_once_and_full_amount_by_default(self):
        app = self._decide(self._closed())
        self.assertEqual((app.refund_amount, app.refund_order_number), (Decimal("50.00"), "15/Q"))
        with self.assertRaises(ValidationError):
            self._decide(app)
        event = app.events.get(action=RetakeEventAction.REFUND_DECIDED)
        self.assertEqual(event.metadata["refund_amount"], "50.00")
        self.assertEqual((event.metadata["partial"], event.actor_id, event.note), (False, self.office.id, REASON))

    def test_accountant_marks_refunded_once_with_date_and_reference(self):
        app = self._decide(self._closed())
        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        for extra in ({"refunded_on": tomorrow}, {"refunded_on": yesterday}, {"reference": ""}, {"refunded_on": "x"}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self._mark(app, **extra)
        app = self._mark(app)
        self.assertEqual(
            (app.refund_state, app.refund_reference, app.refunded_by_id),
            (RetakeRefundState.REFUNDED, "BANK-2026-001", self.accountant.id),
        )
        with self.assertRaises(ValidationError):
            self._mark(app)
        event = app.events.get(action=RetakeEventAction.REFUNDED)
        self.assertEqual(event.metadata["refund_reference"], "BANK-2026-001")
        logs = django_apps.get_model("audit", "AuditLog").objects.filter(resource_id=str(app.pk))
        self.assertTrue(logs.filter(reason="retake_refund_decided").exists())
        self.assertTrue(logs.filter(reason="retake_refunded").exists())

    # ── Append-only / DB ────────────────────────────────────────────────────
    def test_database_freezes_decision_and_blocks_going_back(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger-i")
        app = self._mark(self._decide(self._closed()))
        statements = (
            "UPDATE registrar_retakeapplication SET refund_amount = 1 WHERE id = %s",
            "UPDATE registrar_retakeapplication SET refund_state = 'decided', refunded_at = NULL, "
            "refunded_on = NULL WHERE id = %s",
            "UPDATE registrar_retakeapplication SET refund_reference = 'X' WHERE id = %s",
            "UPDATE registrar_retakeapplicationevent SET note = 'x' WHERE application_id = %s",
        )
        for statement in statements:
            with self.subTest(statement=statement), bypass_rls():
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(statement, [app.pk])
        fresh = self._verified(student=self.other)
        with self.subTest("not closed"), bypass_rls():
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE registrar_retakeapplication SET refund_state = 'decided', refund_amount = 5, "
                    "refund_decided_at = now() WHERE id = %s",
                    [fresh.pk],
                )

    # ── Növbə və tələbə görünüşü ────────────────────────────────────────────
    def test_refunds_tab_for_accountant_without_scores(self):
        app = self._decide(self._closed())
        page = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk&rt_tab=refunds")
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn("Qaytarılacaq ödənişlər", body)
        self.assertIn(f'id="rt-row-{app.id}"', body)
        self.assertIn("15/Q", body)
        self.assertIn('data-rt-action="mark"', body)
        self.assertNotIn("Əsas imtahan", body)
        dean = self.client_for(self.dean).get(f"{PROFILE}?section=retake-desk&rt_tab=refunds").content.decode()
        self.assertNotIn(f'id="rt-row-{app.id}"', dean)  # dekanın tab-ı yoxdur → ilk tab açılır
        self._mark(app)
        pending = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk&rt_tab=refunds")
        self.assertNotIn(f'id="rt-row-{app.id}"', pending.content.decode())
        done = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk&rt_tab=refunds&rt_status=refunded")
        self.assertIn(f'id="rt-row-{app.id}"', done.content.decode())

    def test_decide_button_only_for_org_wide_manage(self):
        app = self._closed()
        office = self.client_for(self.office).get(f"{PROFILE}?section=retake-desk&rt_tab=all").content.decode()
        dean = self.client_for(self.dean).get(f"{PROFILE}?section=retake-desk&rt_tab=all").content.decode()
        marker = f'{reverse("retake:refund", args=[app.id])}" data-rt-action="decide"'
        self.assertIn(marker, office)
        self.assertNotIn(marker, dean)
        self._decide(app)
        office = self.client_for(self.office).get(f"{PROFILE}?section=retake-desk&rt_tab=all").content.decode()
        self.assertNotIn(marker, office)  # bir dəfə
        self.assertIn("Ödənişin qaytarılması qərarı verilib", office)

    def test_student_sees_refund_state(self):
        app = self._decide(self._closed())
        page = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Ödənişin qaytarılması qərarı verilib", page)
        self._mark(app)
        page = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Ödəniş qaytarılıb", page)

    def test_notifications_after_commit(self):
        notification = django_apps.get_model("notifications", "InAppNotification")
        app = self._closed()
        with self.captureOnCommitCallbacks(execute=True):
            self._decide(app)
        with bypass_rls():
            self.assertTrue(
                notification.objects.filter(
                    recipient=self.student, title="Ödənişin qaytarılması qərarı verildi"
                ).exists()
            )
            self.assertTrue(
                notification.objects.filter(recipient=self.accountant, title="Qaytarılacaq ödəniş növbədədir").exists()
            )
        with self.captureOnCommitCallbacks(execute=True):
            self._mark(app)
        with bypass_rls():
            self.assertTrue(notification.objects.filter(recipient=self.student, title="Ödəniş qaytarıldı").exists())

    # ── Review 2026-10-19 (B1): qərar sənədləri qorunan mediadan açılır ─────────
    def _subgroup_with_document(self):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            retake_decisions.approve_subgroup(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                document=pdf("teqdimat.pdf"),
                reason="Tələbə alt qrupda yenidən keçmək istəyir — təqdimat əlavə olunur.",
            )
            app.refresh_from_db()
        return app

    def _access(self, path):
        with bypass_rls():
            return {
                user.username: check_document_access(user, path)
                for user in (
                    self.student,
                    self.other,
                    self.office,
                    self.dean,
                    self.dean_b,
                    self.coordinator,
                    self.accountant,
                )
            }

    def test_refund_and_closure_documents_are_reachable(self):
        app = self._closed("reject")  # bağlanış: əmr № ilə; sənədli variant aşağıda
        with bypass_rls():
            app.refresh_from_db()
        self._decide(app, order_number="", order_date=None, document=pdf("qaytarma.pdf"))
        refund = self._access(app.refund_document.name)
        self.assertEqual(
            refund,
            {
                "rt_student": True,  # sahibi
                "rt_other": False,
                "rt_office": True,
                "rt_dean": True,  # fakültə əhatəsində iz açarı
                "rt_dean_b": False,  # başqa fakültə
                "rt_coord": True,
                "rt_acc": True,  # Mühasibatlıq qaytarılmanı icra edir
            },
        )

    def test_closure_document_follows_trail_keys(self):
        app = self._verified()
        with bypass_rls():
            retake_decisions.reject(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                reason="Ödəniş başqa fənn üçün edilib, müraciət rədd olunur.",
                document=pdf("qerar.pdf"),
            )
            app.refresh_from_db()
        access = self._access(app.closure_document.name)
        self.assertTrue(access["rt_student"] and access["rt_dean"] and access["rt_office"] and access["rt_coord"])
        self.assertFalse(access["rt_other"] or access["rt_dean_b"] or access["rt_acc"])

    def test_subgroup_decision_document_still_works(self):
        app = self._subgroup_with_document()
        access = self._access(app.decision_document.name)
        self.assertTrue(access["rt_student"] and access["rt_dean"])
        self.assertFalse(access["rt_other"] or access["rt_dean_b"] or access["rt_acc"])
        self.assertFalse(check_document_access(self.student, "retake_documents/yoxdur.pdf"))
        self.assertFalse(check_document_access(self.student, ""))

    # ── Review 2026-10-19 (M2): qaytarılma cəhdi bərpa edir (defolt) ────────────
    def _attempts(self):
        rows = retake_eligibility.failed_subjects(student=self.student, organization=self.org)
        row = next(r for r in rows if r["subject"].id == self.subject.id)
        return row["attempts_used"], row["options"]["retake_25"]["allowed"]

    def test_no_show_consumes_until_refund_restores_attempt(self):
        app = self._closed("no_show")
        with bypass_rls():
            self.assertEqual(self._attempts(), (1, False))
        self._decide(app)
        self.assertTrue(app.refund_restores_attempt)
        with bypass_rls():
            self.assertEqual(self._attempts(), (0, True))
            again = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
        self.assertEqual(again.attempt_number, 1)
        self.assertIn(
            "25% cəhdi istifadə olunmuş sayılmır",
            self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode(),
        )

    def test_refund_without_restore_keeps_attempt_consumed(self):
        app = self._closed("no_show")
        url = reverse("retake:refund", args=[app.id])
        data = {
            "action": "decide",
            "reason": REASON,
            "order_number": "15/Q",
            "order_date": today(),
            "restores_attempt": ["0"],  # checkbox işarələnməyib — yalnız gizli «0»
        }
        self.assertEqual(self.client_for(self.office).post(url, data).status_code, 200)
        with bypass_rls():
            app.refresh_from_db()
            self.assertEqual(self._attempts(), (1, False))
        self.assertFalse(app.refund_restores_attempt)
        self.assertFalse(app.events.get(action=RetakeEventAction.REFUND_DECIDED).metadata["restores_attempt"])
        desk = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk&rt_tab=refunds").content.decode()
        self.assertIn("25% cəhdi istifadə olunmuş sayılır", desk)

    def test_checkbox_checked_posts_one(self):
        app = self._closed("no_show")
        data = {"action": "decide", "reason": REASON, "order_number": "1", "order_date": today()}
        data["restores_attempt"] = ["0", "1"]  # gizli «0» + işarələnmiş checkbox «1»
        self.assertEqual(
            self.client_for(self.office).post(reverse("retake:refund", args=[app.id]), data).status_code, 200
        )
        with bypass_rls():
            app.refresh_from_db()
        self.assertTrue(app.refund_restores_attempt)

    # ── Review 2026-10-19 (L4): DB sahə ardıcıllığı ─────────────────────────────
    def test_database_keeps_refund_fields_consistent(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL")
        closed = self._closed("no_show")
        statements = [
            ("UPDATE registrar_retakeapplication SET refund_reference = 'X' WHERE id = %s", closed),
            ("UPDATE registrar_retakeapplication SET refund_reason = 'X' WHERE id = %s", closed),
            ("UPDATE registrar_retakeapplication SET refund_order_number = '1' WHERE id = %s", closed),
            ("UPDATE registrar_retakeapplication SET refunded_on = now()::date WHERE id = %s", closed),
        ]
        for statement, app in statements:
            with self.subTest(statement=statement), bypass_rls():
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(statement, [app.pk])
        decided = self._decide(closed)
        for statement in (
            "UPDATE registrar_retakeapplication SET refund_restores_attempt = false WHERE id = %s",
            "UPDATE registrar_retakeapplication SET refunded_on = now()::date WHERE id = %s",
            "UPDATE registrar_retakeapplication SET refund_reference = 'X' WHERE id = %s",
        ):
            with self.subTest(statement=statement), bypass_rls():
                with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(statement, [decided.pk])


class RefundLocalDateTest(SimpleTestCase):
    def test_fixture_advances_at_university_midnight_and_preserves_chronology_guard(self):
        before = datetime.datetime(2026, 10, 28, 19, 59, tzinfo=datetime.timezone.utc)
        after = datetime.datetime(2026, 10, 28, 20, 1, tzinfo=datetime.timezone.utc)
        with timezone.override("Asia/Baku"):
            with patch.object(timezone, "now", return_value=before):
                collected_day = today()
                self.assertEqual(collected_day, "2026-10-28")
            with patch.object(timezone, "now", return_value=after):
                executed_day = today()
                self.assertEqual(executed_day, "2026-10-29")
                application = SimpleNamespace(refund_decided_at=after)
                self.assertEqual(
                    retake_refund._clean_refund_date(executed_day, application),
                    datetime.date(2026, 10, 29),
                )
                with self.assertRaisesMessage(ValidationError, "qərar tarixindən əvvəl"):
                    retake_refund._clean_refund_date(collected_day, application)
