"""25% follow-up paketinin müstəqil rəyi (2026-10-19) — HIGH-1, MEDIUM-2/3/4/10, LOW-5..9 reqressiyaları."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt, ExamStudentPin, StudentExamAttemptGrant
from apps.exams.public import grant_second_chance
from apps.organizations.models import AcademicPeriod
from apps.registrar import (
    exam_bridge,
    retake_chance,
    retake_closure,
    retake_decisions,
    retake_fees,
    retake_services,
    retake_views,
    retake_window,
)
from apps.registrar.models import (
    FinalGrade,
    ResitRecord,
    RetakeEventAction,
    RetakeStatus,
    RetakeTuition,
    RetakeWindow,
)
from core.constants import AcademicPeriodType, RoleScopeType
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf

PROFILE = "/accounts/profile/"
REASON = "Tələbə təyin olunmuş 25% imtahanına gəlmədi."


class _Base(RetakeBase):
    def setUp(self):
        self.fail_exam(score=12)  # əsas imtahan 12 / 50

    def _apply(self):
        with bypass_rls():
            return retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )

    def _verify(self, app, paid="50"):
        with bypass_rls():
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount=paid
            )
            app.refresh_from_db()
        return app

    def _tuition(self, amount, year="2025/2026"):
        with bypass_rls():
            return RetakeTuition.objects.create(
                organization=self.org, academic_year=year, admission_year=2025, annual_amount=Decimal(amount)
            )


class ClosedApplicationAttemptTest(_Base):
    """HIGH-1: imtahan cəhdi açılmış müraciət bağlananda 25% balı əsas imtahan balını əzmir."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        with bypass_rls():
            self.exam = Exam.objects.create(
                title="INF101 yekun",
                author=self.teacher,
                organization=self.org,
                subject=self.subject,
                exam_type="test",
                exam_type_extended="final",
                is_active=True,
                is_public=False,
                max_attempts_per_user=1,
                total_duration_minutes=60,
                start_datetime=now - datetime.timedelta(hours=1),
                end_datetime=now + datetime.timedelta(hours=3),
            )
            original = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                status="submitted",
                attempt_number=1,
                finished_at=now - datetime.timedelta(days=30),
            )
            ExamAttempt.objects.filter(pk=original.pk).update(started_at=now - datetime.timedelta(days=30))

    def _granted(self):
        app = self._verify(self._apply())
        exam = {
            "id": self.exam.pk,
            "title": self.exam.title,
            "exam_type": "test",
            "category": "final",
            "subject_id": self.subject.id,
        }
        with bypass_rls():
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            # Real axın: «Yenidən imtahan cəhdi» (grant + PIN) + rəsmi qeyd bir tranzaksiyada.
            grant_second_chance(exam=self.exam, students=[self.student], extra=1, granted_by=self.dean)
            cleaned = retake_chance.validate(
                organization=self.org, exam=exam, students=[self.student], reason="retake_25"
            )
            retake_chance.record(
                organization=self.org, exam=exam, students=[self.student], cleaned=cleaned, extra=1, actor=self.dean
            )
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)
        return app

    def _attempt(self, status="submitted", number=2):
        with bypass_rls():
            return ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                status=status,
                attempt_number=number,
                finished_at=None if status == "in_progress" else timezone.now() + datetime.timedelta(minutes=50),
            )

    def _close(self, app, action="no_show"):
        with bypass_rls():
            return retake_closure.close(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                action=action,
                reason=REASON,
                order_number="91/D",
                order_date="2026-10-19",
            )

    def test_closure_revokes_extra_attempt_and_pin(self):
        app = self._granted()
        with bypass_rls():
            self.assertEqual(
                StudentExamAttemptGrant.objects.get(exam=self.exam, student=self.student).extra_attempts, 1
            )
            self.assertEqual(self.exam.attempts_left_for(self.student), 1)
        self._close(app)
        with bypass_rls():
            app.refresh_from_db()
            grant = StudentExamAttemptGrant.objects.get(exam=self.exam, student=self.student)
            pin = ExamStudentPin.objects.filter(exam=self.exam, student=self.student).first()
            event = app.events.get(action=RetakeEventAction.NO_SHOW)
            self.assertEqual(self.exam.attempts_left_for(self.student), 0)
        self.assertEqual(app.status, RetakeStatus.NO_SHOW)
        self.assertEqual(grant.extra_attempts, 0)
        self.assertTrue(pin is None or pin.revoked_at is not None)
        self.assertEqual(event.metadata["revoked_exam_access"][0]["revoked"], 1)

    def test_closure_refused_while_attempt_in_progress(self):
        app = self._granted()
        self._attempt(status="in_progress")
        with self.assertRaisesMessage(ValidationError, "hazırda cəhd edir"):
            self._close(app, action="withdraw")
        with bypass_rls():
            app.refresh_from_db()
            self.assertEqual(
                StudentExamAttemptGrant.objects.get(exam=self.exam, student=self.student).extra_attempts, 1
            )
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)

    def test_closure_refused_while_written_attempt_is_ungraded(self):
        app = self._granted()
        with bypass_rls():
            Exam.objects.filter(pk=self.exam.pk).update(exam_type="written")
        self._attempt(status="submitted")  # teacher_score boş → yoxlanmayıb
        with self.assertRaisesMessage(ValidationError, "hələ yoxlanmayıb"):
            self._close(app, action="reject")
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)

    def test_attempt_of_closed_application_is_not_written_anywhere(self):
        app = self._granted()
        self._close(app)
        attempt = self._attempt(status="submitted")  # gecikmiş / geri alınmamış cəhd
        with bypass_rls():
            result = exam_bridge.record_exam_result(
                student=self.student,
                subject_id=self.subject.id,
                organization=self.org,
                score_percent=90,
                attempt=attempt,
            )
            app.refresh_from_db()
            exam_score = FinalGrade.objects.get(enrollment=self.enrollment).exam_score
            resit = ResitRecord.objects.filter(enrollment=self.enrollment).first()
        self.assertIsNone(result)
        self.assertEqual(exam_score, Decimal("12"))  # əsas imtahan balı toxunulmaz
        self.assertTrue(resit is None or resit.resit_score is None)
        self.assertEqual(app.status, RetakeStatus.NO_SHOW)

    def test_closure_without_exam_grant_still_works(self):
        app = self._verify(self._apply())
        with bypass_rls():
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
        self._close(app)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.NO_SHOW)


@override_settings(UNIVERSITY_MODE=True)
class WindowReviewTest(_Base):
    """MEDIUM-2 (vaxtı keçmiş pəncərə), MEDIUM-4 (boş vəziyyət), dövr seçimi, LOW-7 (org-wide), LOW-8 (404)."""

    def _center(self, scope=RoleScopeType.ORGANIZATION, unit=None, name="rt_center_r"):
        return self._staff(name, ["exam_center.decide"], scope, unit)

    def test_expired_window_is_auto_closed_on_reopen(self):
        center = self._center()
        now = timezone.now()
        with bypass_rls():
            retake_window.close_window(actor=center, organization=self.org, window_id=self.window.pk)
            expired = RetakeWindow.objects.create(
                organization=self.org,
                period=self.current,
                opens_at=now - datetime.timedelta(days=3),
                closes_at=now - datetime.timedelta(days=1),
            )
        opened = self.client_for(center).post(reverse("retake:window_open"), {"period": str(self.current.pk)})
        self.assertEqual(opened.status_code, 200, opened.content)
        with bypass_rls():
            expired.refresh_from_db()
            self.assertIsNotNone(retake_window.current(self.org))
        self.assertEqual(expired.closed_at, expired.closes_at)
        self.assertIsNone(expired.closed_by)

    def test_every_unclosed_row_has_a_close_button(self):
        center = self._center()
        with bypass_rls():
            retake_window.close_window(actor=center, organization=self.org, window_id=self.window.pk)
            scheduled = RetakeWindow.objects.create(
                organization=self.org, period=self.current, opens_at=timezone.now() + datetime.timedelta(days=5)
            )
        body = self.client_for(center).get(f"{PROFILE}?section=retake-windows").content.decode()
        self.assertEqual(body.count(reverse("retake:window_close", args=[scheduled.pk])), 2)  # kart + tarixçə
        self.assertNotIn(reverse("retake:window_close", args=[self.window.pk]), body)

    def test_period_picker_is_current_and_upcoming_only(self):
        center = self._center()
        with bypass_rls():
            self.assertEqual([p.pk for p in retake_window.selectable_periods(self.org)], [self.current.pk])
            with self.assertRaises(ValidationError):
                retake_window.open_window(actor=center, organization=self.org, period=self.past)
        body = self.client_for(center).get(f"{PROFILE}?section=retake-windows").content.decode()
        self.assertIn(self.current.name, body)
        self.assertNotIn(f'<option value="{self.past.pk}"', body)

    def test_no_window_after_deploy_shows_calls_to_action(self):
        with bypass_rls():
            RetakeWindow.objects.filter(organization=self.org).delete()
        center_body = self.client_for(self._center()).get(f"{PROFILE}?section=retake-windows").content.decode()
        self.assertIn("Hələ pəncərə açılmayıb — müraciət qəbulu üçün pəncərə açın", center_body)
        student_body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("Müraciət pəncərəsi bağlıdır — imtahan mərkəzi açanda burada görünəcək", student_body)
        with bypass_rls(), self.assertRaises(ValidationError):  # alt qrup da eyni pəncərəyə bağlıdır
            retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )

    def test_unit_scoped_keys_cannot_manage_org_settings(self):
        unit_center = self._center(RoleScopeType.UNIT, self.faculty, name="rt_center_unit")
        unit_acc = self._staff("rt_acc_unit", ["retake.payment_verify"], RoleScopeType.UNIT, self.faculty)
        with bypass_rls():
            self.assertFalse(retake_window.can_manage(unit_center, self.org))
            self.assertFalse(retake_fees.can_manage(unit_acc, self.org))
            self.assertTrue(retake_fees.can_manage(self.accountant, self.org))
        denied = self.client_for(unit_center).post(reverse("retake:window_open"), {"period": str(self.current.pk)})
        self.assertEqual(denied.status_code, 403)
        data = {"academic_year": "2025/2026", "admission_year": "2025", "annual_amount": "2400"}
        self.assertEqual(self.client_for(unit_acc).post(reverse("retake:tuition_save"), data).status_code, 403)

    def test_missing_window_or_tuition_maps_to_404(self):
        for model in (RetakeWindow, RetakeTuition):

            def _raise(model=model):
                raise model.DoesNotExist

            with self.assertRaises(Http404):
                retake_views._run(_raise, success="ok")
        missing = reverse("retake:tuition_delete", args=[uuid.uuid4()])
        self.assertEqual(self.client_for(self.accountant).post(missing).status_code, 404)


@override_settings(UNIVERSITY_MODE=True)
class FeeReviewTest(_Base):
    """MEDIUM-3 (snapshot), MEDIUM-10 (tədris ili), LOW-5 (kredit), LOW-6 (məbləğ > 0), LOW-9 (il formatı)."""

    def test_submitted_event_keeps_fee_and_verify_keeps_both_estimates(self):
        row = self._tuition("2400")  # 2400 × 25% × 5/60 = 50.00
        app = self._apply()
        with bypass_rls():
            submitted = app.events.get(action=RetakeEventAction.SUBMITTED)
            RetakeTuition.objects.filter(pk=row.pk).update(annual_amount=Decimal("3000"))  # → 62.50
        self.assertEqual(submitted.metadata["expected_fee"], "50.00")
        self.assertEqual(submitted.metadata["fee_inputs"]["annual_amount"], "2400.00")
        app = self._verify(app, paid="50")
        with bypass_rls():
            verified = app.events.get(action=RetakeEventAction.PAYMENT_VERIFIED)
        self.assertEqual(verified.metadata["expected_at_submit"], "50.00")
        self.assertEqual(verified.metadata["expected_at_verify"], "62.50")
        self.assertEqual(verified.metadata["fee_inputs_at_submit"]["annual_amount"], "2400.00")

    def test_missing_recompute_keeps_old_amount_and_inputs(self):
        row = self._tuition("2400")
        app = self._apply()
        with bypass_rls():
            RetakeTuition.objects.filter(pk=row.pk).delete()
        app = self._verify(app, paid="50")
        with bypass_rls():
            verified = app.events.get(action=RetakeEventAction.PAYMENT_VERIFIED)
        self.assertEqual(app.expected_fee, Decimal("50.00"))
        self.assertEqual(app.fee_inputs["annual_amount"], "2400.00")  # məbləğ və girişləri uyğun qalır
        self.assertEqual(verified.metadata["fee_inputs"]["annual_amount"], "2400.00")
        self.assertIsNone(verified.metadata["expected_at_verify"])

    def test_fee_uses_current_period_year_not_failed_period_year(self):
        with bypass_rls():
            new_current = AcademicPeriod.objects.create(
                organization=self.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            AcademicPeriod.objects.filter(pk=self.current.pk).update(is_current=False)
        self._tuition("2400", year="2025/2026")  # kəsr dövrünün ili — İSTİFADƏ OLUNMAMALIDIR
        with bypass_rls():
            context = retake_fees.student_context(self.student, self.org)
            first = retake_fees.estimate(context=context, period=self.past, subject=self.subject)
        self.assertIsNone(first["amount"])
        self.assertEqual(first["inputs"]["academic_year"], new_current.academic_year)
        self._tuition("3600", year="2026/2027")  # 3600 × 25% × 5/60 = 75.00
        app = self._apply()
        self.assertEqual(app.expected_fee, Decimal("75.00"))
        self.assertEqual(app.fee_inputs["academic_year"], "2026/2027")
        self.assertEqual(app.fee_inputs["academic_year_source"], retake_fees.YEAR_CURRENT)
        body = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertIn("(2026/2027 tədris ilinin haqqı ilə)", body)
        desk = (
            self.client_for(self.accountant)
            .get(f"{PROFILE}?section=retake-desk&rt_tab=payments&rt_status=")
            .content.decode()
        )
        self.assertIn("(2026/2027 tədris ilinin haqqı ilə)", desk)

    def test_zero_credits_give_no_amount(self):
        self._tuition("2400")
        with bypass_rls():
            type(self.subject).objects.filter(pk=self.subject.pk).update(ects=0)
            self.subject.refresh_from_db()
            context = retake_fees.student_context(self.student, self.org)
            fee = retake_fees.estimate(context=context, period=self.past, subject=self.subject)
        self.assertIsNone(fee["amount"])
        self.assertEqual(fee["inputs"]["missing"], "credits")

    def test_paid_amount_must_be_positive(self):
        app = self._apply()
        with bypass_rls(), self.assertRaisesMessage(ValidationError, "0-dan böyük"):
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount="0"
            )

    def test_tuition_year_must_be_known_or_well_formed(self):
        url = reverse("retake:tuition_save")
        client = self.client_for(self.accountant)
        base = {"admission_year": "2025", "annual_amount": "2400"}
        self.assertEqual(client.post(url, {**base, "academic_year": "2026"}).status_code, 400)
        self.assertEqual(client.post(url, {**base, "academic_year": "2026/2028"}).status_code, 400)
        known = client.post(url, {**base, "academic_year": "2025/2026"})
        self.assertEqual(known.status_code, 200, known.content)
        self.assertNotIn("warning", known.json())
        future = client.post(url, {**base, "academic_year": "2030/2031"})
        self.assertEqual(future.status_code, 200, future.content)
        self.assertIn("akademik dövr yoxdur", future.json()["warning"])
        body = client.get(f"{PROFILE}?section=retake-desk&rt_tab=fees").content.decode()
        self.assertIn('<option value="2025/2026">', body)
