"""Rəy 2026-10-21 (R08): rəsmi bal yazıları audit FAIL-CLOSED-dur.

Əvvəl yekun imtahan / bonus / təkrar balı, 25% nəticəsi və toplu imtahan balı audit sətri yazılmasa belə
commit olunurdu (best-effort). İndi audit INSERT-i düşsə ``AuditWriteFailed`` atılır, domen yazısı geri qayıdır
və istifadəçi yolu aydın xəta göstərir. Hər yol üçün: (1) audit düşür → bal sətri DƏYİŞMİR; (2) normal yol
həm balı, həm audit sətrini yazır.

Xəta yalnız ``registrar.grade.*`` audit sətrinin INSERT-ində simulyasiya olunur (timeout / lock / disk).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import DatabaseError, connection
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import exam_score_bulk
from apps.registrar import exam_score_entry as service
from apps.registrar import finals, retake_decisions
from apps.registrar.audit_write import AuditWriteFailed, audit_failure_message
from apps.registrar.exam_score_period_lock import CURRENT_PERIOD
from apps.registrar.models import ExamScoreEntry, FinalGrade, ResitRecord, ResitStatus, RetakeStatus
from apps.registrar.tests.test_exam_score_bulk_2026_10_08 import _seed
from core.rls import bypass_rls

from .test_retake_2026_10_18 import _Helpers


def _flat(values):
    """INSERT parametrləri — tək sətir (düz), ``executemany`` və ya toplu UNNEST (sütun massivləri)."""
    for value in values or ():
        if isinstance(value, (list, tuple)):
            yield from _flat(value)
        else:
            yield value


def _audit_insert_breaker(predicate):
    def wrapper(execute, sql, params, many, context):
        if sql.lstrip().upper().startswith('INSERT INTO "AUDIT_AUDITLOG"'):
            if any(isinstance(value, str) and predicate(value) for value in _flat(params)):
                raise DatabaseError("simulated audit insert failure")
        return execute(sql, params, many, context)

    return wrapper


#: Yalnız ``registrar.grade.*`` audit sətirlərinin INSERT-ini sındır.
_fail_grade_audit = _audit_insert_breaker(lambda value: value.startswith("registrar.grade."))


def _grade_audits(offering, kind):
    return AuditLog.objects.filter(resource_type=f"registrar.grade.{kind}", resource_id=str(offering.pk)).count()


class FinalsFailClosedTest(TestCase):
    STUDENTS = 3

    @classmethod
    def setUpTestData(cls):
        _seed(cls, cls.STUDENTS)
        cls.offering = cls.offerings[0]

    def _enrollments(self):
        return list(self.offering.enrollments.select_related("student").order_by("student__username"))

    # ── finals.set_exam_score ───────────────────────────────────────────────
    def test_exam_score_rolls_back_when_audit_fails(self):
        enrollment = self._enrollments()[0]
        with bypass_rls():
            with connection.execute_wrapper(_fail_grade_audit), self.assertRaises(AuditWriteFailed):
                finals.set_exam_score(enrollment=enrollment, score=30, by_user=self.center)
            self.assertFalse(FinalGrade.objects.filter(enrollment=enrollment, exam_score__isnull=False).exists())
            self.assertEqual(_grade_audits(self.offering, "final"), 0)

    def test_exam_score_normal_path_writes_score_and_audit(self):
        enrollment = self._enrollments()[0]
        with bypass_rls():
            finals.set_exam_score(enrollment=enrollment, score=30, by_user=self.center)
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal("30"))
            self.assertEqual(_grade_audits(self.offering, "final"), 1)

    def test_existing_score_is_not_changed_when_audit_fails(self):
        enrollment = self._enrollments()[0]
        with bypass_rls():
            finals.set_exam_score(enrollment=enrollment, score=30, by_user=self.center)
            with connection.execute_wrapper(_fail_grade_audit), self.assertRaises(AuditWriteFailed):
                finals.set_exam_score(enrollment=enrollment, score=45, by_user=self.center)
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal("30"))
            self.assertEqual(_grade_audits(self.offering, "final"), 1)

    # ── finals.set_resit_score ──────────────────────────────────────────────
    def _resit(self, enrollment):
        return ResitRecord.objects.create(
            organization=self.org, enrollment=enrollment, reason="exam", status=ResitStatus.ELIGIBLE
        )

    def test_resit_score_rolls_back_when_audit_fails(self):
        enrollment = self._enrollments()[1]
        with bypass_rls():
            resit = self._resit(enrollment)
            with connection.execute_wrapper(_fail_grade_audit), self.assertRaises(AuditWriteFailed):
                finals.set_resit_score(enrollment=enrollment, score=35, by_user=self.center)
            resit.refresh_from_db()
            self.assertIsNone(resit.resit_score)
            self.assertEqual(resit.status, ResitStatus.ELIGIBLE)
            finals.set_resit_score(enrollment=enrollment, score=35, by_user=self.center)
            resit.refresh_from_db()
            self.assertEqual(resit.resit_score, Decimal("35"))
            self.assertEqual(_grade_audits(self.offering, "resit"), 1)

    # ── finals.set_final_extras (bonus) ─────────────────────────────────────
    def test_bonus_rolls_back_when_audit_fails(self):
        enrollment = self._enrollments()[2]
        with bypass_rls():
            with connection.execute_wrapper(_fail_grade_audit), self.assertRaises(AuditWriteFailed):
                finals.set_final_extras(enrollment=enrollment, bonus="5", comment="yaxşı", by_user=self.center)
            grade = FinalGrade.objects.filter(enrollment=enrollment).first()
            self.assertTrue(grade is None or (grade.bonus == 0 and grade.comment == ""))
            finals.set_final_extras(enrollment=enrollment, bonus="5", by_user=self.center)
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).bonus, Decimal("5"))
            self.assertEqual(_grade_audits(self.offering, "final"), 1)

    # ── jurnalın «Yekun» əməli (istifadəçi yolu) ────────────────────────────
    def test_journal_save_finals_reports_audit_failure_and_keeps_rows_unchanged(self):
        from django.contrib.auth import get_user_model
        from django.contrib.messages import get_messages
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from apps.registrar import journal_finals

        admin = get_user_model().objects.create_superuser("r08_admin", "r08_admin@qku.edu.az", "pw")
        resit_target, bonus_target = self._enrollments()[:2]
        with bypass_rls():
            resit = self._resit(resit_target)
            request = RequestFactory().post("/", {f"resit__{resit_target.id}": "35", f"bonus__{bonus_target.id}": "4"})
            request.user = admin
            request.session = SessionStore()
            request._messages = FallbackStorage(request)
            with connection.execute_wrapper(_fail_grade_audit):
                response = journal_finals.handle_save_finals(request, self.offering)
            self.assertEqual(response.status_code, 302)
            texts = [str(message) for message in get_messages(request)]
            self.assertTrue(any(audit_failure_message() in text for text in texts), texts)
            resit.refresh_from_db()
            self.assertIsNone(resit.resit_score)
            grade = FinalGrade.objects.filter(enrollment=bonus_target).first()
            self.assertTrue(grade is None or grade.bonus == 0)

    # ── toplu imtahan balı (save_roster_scores → exam_score_bulk) ───────────
    def _rows(self, score="30"):
        return [{"enrollment_id": str(e.id), "score": score} for e in self._enrollments()]

    def test_bulk_save_writes_nothing_and_reports_every_row_when_audit_fails(self):
        with bypass_rls():
            with (
                connection.execute_wrapper(_fail_grade_audit),
                self.assertLogs("apps.registrar.exam_score_bulk", level="ERROR"),
            ):
                result = service.save_roster_scores(offering=self.offering, rows=self._rows(), by_user=self.center)
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["failed"], self.STUDENTS)
            self.assertEqual(result["written_ids"], [])
            self.assertTrue(all(message == audit_failure_message() for _name, message in result["errors"]))
            enrollment_ids = [e.id for e in self._enrollments()]
            self.assertFalse(FinalGrade.objects.filter(enrollment_id__in=enrollment_ids).exists())
            self.assertFalse(ExamScoreEntry.objects.filter(enrollment_id__in=enrollment_ids).exists())
            self.assertEqual(_grade_audits(self.offering, "final"), 0)

    def test_bulk_save_normal_path_writes_scores_entries_and_audits(self):
        with bypass_rls():
            result = service.save_roster_scores(offering=self.offering, rows=self._rows(), by_user=self.center)
            enrollment_ids = [e.id for e in self._enrollments()]
            self.assertEqual(result["written"], self.STUDENTS)
            self.assertEqual(FinalGrade.objects.filter(enrollment_id__in=enrollment_ids).count(), self.STUDENTS)
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment_id__in=enrollment_ids).count(), self.STUDENTS)
            self.assertEqual(_grade_audits(self.offering, "final"), self.STUDENTS)

    def test_bulk_entry_ledger_audit_failure_also_rolls_back(self):
        fail_entry_audit = _audit_insert_breaker(lambda value: value == "registrar.exam_score_entry")
        with bypass_rls():
            with (
                connection.execute_wrapper(fail_entry_audit),
                self.assertLogs("apps.registrar.exam_score_bulk", level="ERROR"),
            ):
                result = service.save_roster_scores(offering=self.offering, rows=self._rows(), by_user=self.center)
            self.assertEqual(result["written"], 0)
            enrollment_ids = [e.id for e in self._enrollments()]
            self.assertFalse(FinalGrade.objects.filter(enrollment_id__in=enrollment_ids).exists())
            self.assertEqual(_grade_audits(self.offering, "final"), 0)

    def test_sequential_path_fails_only_the_row_whose_audit_failed(self):
        first, second = self._enrollments()[:2]
        rows = [
            {"enrollment_id": str(first.id), "score": "30"},
            {"enrollment_id": str(first.id), "score": "30"},  # dublikat → sətir-sətir yol
            {"enrollment_id": str(second.id), "score": "25"},
        ]
        with bypass_rls():
            with (
                connection.execute_wrapper(_fail_grade_audit),
                self.assertLogs("apps.registrar.exam_score_bulk", level="ERROR"),
            ):
                result = exam_score_bulk.save_rows(
                    offering=self.offering, rows=rows, by_user=self.center, policy=CURRENT_PERIOD
                )
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["failed"], 3)
            self.assertFalse(FinalGrade.objects.filter(enrollment__in=[first, second]).exists())


class RetakeResultFailClosedTest(_Helpers):
    """25% nəticəsi: audit düşsə ``ResitRecord`` və müraciət dəyişmir; view aydın xəta qaytarır."""

    def test_service_rolls_back_resit_and_application(self):
        self.fail_exam()
        with bypass_rls():
            app = self._admitted()
            with connection.execute_wrapper(_fail_grade_audit), self.assertRaises(AuditWriteFailed):
                retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=app.id, score=40)
            app.refresh_from_db()
            self.assertNotEqual(app.status, RetakeStatus.COMPLETED)
            self.assertIsNone(app.result_score)
            resit = ResitRecord.objects.filter(enrollment=self.enrollment).first()
            self.assertTrue(resit is None or resit.resit_score is None)

    def test_view_shows_clear_error_and_normal_path_writes_both(self):
        self.fail_exam()
        with bypass_rls():
            app = self._admitted()
        client = self.client_for(self.dean)
        with connection.execute_wrapper(_fail_grade_audit):
            response = client.post(reverse("retake:result", args=[app.id]), {"score": "41"})
        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["code"], "audit_failed")
        self.assertEqual(response.json()["error"], audit_failure_message())
        response = client.post(reverse("retake:result", args=[app.id]), {"score": "41"})
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.assertEqual(ResitRecord.objects.get(enrollment=self.enrollment).resit_score, Decimal("41"))
            self.assertEqual(_grade_audits(self.offering, "resit"), 1)
