"""Audit 2026-09-28, iş paketi B1 — jurnal bütövlüyü reqressiya testləri.

* DB-01 — best-effort audit INSERT-i düşəndə qiymət yazısı səssizcə geri qayıtmır;
* J-01  — «Yekun» əməli imtahan balını ExamScoreEntry sübutu + dövr kilidi ilə yazır;
  zibil 0-a çevrilmir;
* J-02  — ``update_lesson`` saat aralığı, dublikat slot, audit izi;
* J-03  — komponent balında «abc»/«NaN»/«Infinity» rədd olunur;
* J-05  — qayıb xanasına sənədli bal düzəlişi rədd olunur;
* J-09  — ləğv edilmiş açılışa yazı yoxdur.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import corrections, finals, grade_audit, gradebook, journal_access, services
from apps.registrar.audit_write import create_audit_row
from apps.registrar.models import (
    AssessmentComponent,
    AttendanceStatus,
    ComponentScore,
    CorrectionField,
    CorrectionReason,
    Enrollment,
    ExamScoreEntry,
    FinalGrade,
    Lesson,
    LessonKind,
    LessonMark,
    Subject,
)
from apps.registrar.models.grading_choices import ComponentKind
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

T0830 = datetime.time(8, 30)
T1000 = datetime.time(10, 0)


def _fail_audit_insert(execute, sql, params, many, context):
    """Yalnız ``audit_auditlog`` INSERT-ini sındır (timeout / lock / disk xətası simulyasiyası)."""
    if sql.lstrip().upper().startswith('INSERT INTO "AUDIT_AUDITLOG"'):
        raise DatabaseError("simulated audit insert failure")
    return execute(sql, params, many, context)


class _JournalFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("b1_owner", "b1_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="B1 Univ",
                slug="b1-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="b1-g1", unit_type=OrgUnitType.GROUP
            )
            today = timezone.localdate()
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.old_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Old",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date="2023-09-01",
                end_date="2024-01-31",
                is_current=False,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="B1101", name="X")
            cls.teacher = User.objects.create_user("b1_teacher", "b1_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("b1_student", "b1_student@qku.edu.az", "pw")
            cls.su = User.objects.create_user("b1_su", "b1_su@qku.edu.az", "pw", is_superuser=True)
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)
            cls.old_offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.old_period, group=cls.group
            )
            cls.old_offering.instructor = cls.teacher
            cls.old_offering.save(update_fields=["instructor"])
            cls.old_enrollment = Enrollment.objects.create(
                organization=cls.org, student=cls.student, offering=cls.old_offering
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _lesson(self, start=T0830, end=T1000, kind=LessonKind.SEMINAR):
        return gradebook.create_lesson(
            offering=self.offering,
            date=timezone.localdate(),
            kind=kind,
            start_time=start,
            end_time=end,
            created_by=self.teacher,
        )


class BestEffortAuditSavepointTest(_JournalFixture):
    """DB-01: audit INSERT xətası artıq bütün jurnal yazısını geri qaytarmır."""

    def test_audit_insert_failure_keeps_marks(self):
        with bypass_rls():
            lesson = self._lesson()
            with self.assertLogs("apps.registrar.audit_write", level="ERROR"):
                with connection.execute_wrapper(_fail_audit_insert):
                    result = gradebook.save_marks(
                        offering=self.offering,
                        entries=[
                            {
                                "lesson_id": str(lesson.pk),
                                "enrollment_id": str(self.enrollment.pk),
                                "status": AttendanceStatus.PRESENT,
                                "score": "8",
                            }
                        ],
                        by_user=self.teacher,
                        enforce_day=False,
                        report=True,
                    )
            self.assertEqual(result["written"], 1)
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
        self.assertEqual(mark.score, Decimal("8"))

    def test_fail_closed_audit_still_raises(self):
        with bypass_rls():
            with connection.execute_wrapper(_fail_audit_insert):
                with self.assertRaises(DatabaseError):
                    grade_audit.log_grade_changes(
                        offering=self.offering,
                        by_user=self.teacher,
                        kind="mark",
                        changes=[{"student": "—", "item": "x", "old": "1", "new": "2"}],
                        fail_closed=True,
                    )

    def test_best_effort_failure_leaves_transaction_usable(self):
        with bypass_rls():
            with self.assertLogs("apps.registrar.audit_write", level="ERROR"):
                with connection.execute_wrapper(_fail_audit_insert):
                    ok = create_audit_row(
                        user=None,
                        organization=self.org,
                        action="update",
                        resource_type="registrar.test",
                        resource_id="1",
                    )
            self.assertFalse(ok)
            # Tranzaksiya zəhərlənməyib — növbəti sorğu işləyir.
            self.assertTrue(Enrollment.objects.filter(pk=self.enrollment.pk).exists())


class SaveFinalsLedgerTest(_JournalFixture):
    """J-01: journal «save_finals» → ExamScoreEntry + dövr kilidi; zibil 0 deyil."""

    def _post(self, offering, data):
        payload = {"action": "save_finals", **data}
        return self._client(self.su).post(reverse("registrar:journal_detail", args=[offering.id]), payload)

    def test_first_entry_goes_through_ledger(self):
        resp = self._post(self.offering, {f"exam__{self.enrollment.id}": "42"})
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("42"))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_garbage_does_not_zero_existing_score(self):
        self._post(self.offering, {f"exam__{self.enrollment.id}": "40"})
        self._post(self.offering, {f"exam__{self.enrollment.id}": "abc"})
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("40"))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_change_without_submission_is_rejected(self):
        self._post(self.offering, {f"exam__{self.enrollment.id}": "40"})
        resp = self._post(self.offering, {f"exam__{self.enrollment.id}": "45"})
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("40"))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_past_period_score_change_is_blocked(self):
        with bypass_rls():
            FinalGrade.objects.create(organization=self.org, enrollment=self.old_enrollment, exam_score=Decimal("40"))
        self._post(self.old_offering, {f"exam__{self.old_enrollment.id}": "0"})
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.old_enrollment).exam_score, Decimal("40"))
            self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.old_enrollment).exists())

    def test_clamp_rejects_non_numeric(self):
        for raw in ("abc", "NaN", "Infinity", " "):
            with self.assertRaises(ValidationError):
                finals._clamp(raw, 50)
        self.assertEqual(finals._clamp("70", 50), Decimal("50"))
        self.assertEqual(finals._clamp("-3", 50), Decimal("0"))

    def test_bonus_garbage_keeps_existing_bonus(self):
        with bypass_rls():
            finals.set_final_extras(enrollment=self.enrollment, bonus="3", by_user=self.teacher)
        self._post(self.offering, {f"bonus__{self.enrollment.id}": "abc"})
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).bonus, Decimal("3"))


class UpdateLessonRulesTest(_JournalFixture):
    """J-02: update_lesson — saat 1..MAX_SLOT_HOURS, dublikat slot yoxdur, audit izi."""

    def test_zero_or_oversized_hours_rejected(self):
        with bypass_rls():
            lesson = self._lesson()
            for bad in (0, 9, -1):
                with self.assertRaises(gradebook.LessonRuleError):
                    gradebook.update_lesson(lesson=lesson, hours=bad, by_user=self.teacher)
            lesson.refresh_from_db()
        self.assertEqual(lesson.hours, gradebook.DEFAULT_LESSON_HOURS)

    def test_duplicate_slot_rejected(self):
        with bypass_rls():
            self._lesson()
            other = self._lesson(start=datetime.time(10, 10), end=datetime.time(11, 40))
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(
                    lesson=other,
                    start_time=datetime.time(8, 30),
                    end_time=datetime.time(10, 0),
                    by_user=self.teacher,
                )
            self.assertEqual(
                Lesson.objects.filter(
                    offering=self.offering, date=timezone.localdate(), start_time=datetime.time(8, 30)
                ).count(),
                1,
            )

    def test_hours_change_is_audited_and_recomputes_absence(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            lesson = self._lesson()
            gradebook.save_marks(
                offering=self.offering,
                entries=[
                    {
                        "lesson_id": str(lesson.pk),
                        "enrollment_id": str(self.enrollment.pk),
                        "status": AttendanceStatus.ABSENT,
                    }
                ],
                by_user=self.teacher,
            )
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 2)
            self.assertTrue(gradebook.update_lesson(lesson=lesson, hours=1, by_user=self.teacher))
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 1)
            log = (
                AuditLog.objects.filter(resource_type="registrar.grade.mark", resource_id=str(self.offering.pk))
                .order_by("-created_at")
                .first()
            )
        self.assertIsNotNone(log)
        self.assertEqual(log.user_id, self.teacher.pk)
        self.assertEqual((log.changes[0]["old"], log.changes[0]["new"]), ("2", "1"))

    def test_view_rejects_zero_hours(self):
        with bypass_rls():
            lesson = self._lesson()
        resp = self._client(self.teacher).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            {"action": "update_lesson", "lesson_hours": "0", "lesson_time": "08:30|10:00"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            lesson.refresh_from_db()
        self.assertEqual(lesson.hours, gradebook.DEFAULT_LESSON_HOURS)


class ComponentScoreParsingTest(_JournalFixture):
    """J-03: rəqəm olmayan / sonsuz komponent balı yazılmır, 500 vermir."""

    def test_invalid_values_keep_existing_score(self):
        with bypass_rls():
            comp = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                name="Midterm",
                kind=ComponentKind.KOLLOKVIUM,
                max_score=20,
            )

            def _save(raw):
                return gradebook.save_component_scores(
                    offering=self.offering,
                    entries=[{"component_id": comp.id, "enrollment_id": self.enrollment.id, "score": raw}],
                    bypass_edit_window=True,
                    report=True,
                )

            self.assertEqual(_save("15")["written"], 1)
            for raw in ("abc", "NaN", "Infinity", "-Infinity"):
                self.assertEqual(_save(raw), {"written": 0, "rejected": 1})
                self.assertEqual(ComponentScore.objects.get(component=comp).score, Decimal("15"))
            # Sonlu kənar dəyər əvvəlki kimi tavana sıxılır.
            self.assertEqual(_save("25")["written"], 1)
            self.assertEqual(ComponentScore.objects.get(component=comp).score, Decimal("20"))


class ScoreCorrectionOnAbsenceTest(_JournalFixture):
    """J-05: qayıb xanasına sənədli bal düzəlişi rədd olunur."""

    def test_score_correction_on_absent_cell_rejected(self):
        with bypass_rls():
            lesson = self._lesson()
            gradebook.save_marks(
                offering=self.offering,
                entries=[
                    {
                        "lesson_id": str(lesson.pk),
                        "enrollment_id": str(self.enrollment.pk),
                        "status": AttendanceStatus.ABSENT,
                    }
                ],
                by_user=self.teacher,
            )
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            with self.assertRaises(ValidationError):
                corrections.apply_correction(
                    mark=mark,
                    field=CorrectionField.SCORE,
                    new_score="7",
                    reason=CorrectionReason.TECHNICAL,
                    note="səhv",
                    document=SimpleUploadedFile("doc.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
                    by_user=self.su,
                )
            mark.refresh_from_db()
        self.assertIsNone(mark.score)
        self.assertEqual(mark.status, AttendanceStatus.ABSENT)


class CancelledOfferingWriteTest(_JournalFixture):
    """J-09: ləğv edilmiş açılışın jurnalına URL ilə yazı getmir, oxu qalır."""

    def setUp(self):
        with bypass_rls():
            self.lesson = self._lesson()
            self.offering.is_active = False
            self.offering.save(update_fields=["is_active"])

    def test_direct_editor_denied_but_page_opens(self):
        self.assertFalse(journal_access.is_direct_editor(self.teacher, self.offering))
        client = self._client(self.teacher)
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        self.assertEqual(client.get(url).status_code, 200)
        resp = client.post(
            url,
            {
                "action": "save_marks",
                f"att__{self.lesson.id}__{self.enrollment.id}": AttendanceStatus.ABSENT,
            },
        )
        self.assertEqual(resp.status_code, 404)

    def test_lesson_action_denied(self):
        resp = self._client(self.teacher).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, self.lesson.id]),
            {"action": "update_lesson", "lesson_hours": "1"},
        )
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.lesson.refresh_from_db()
            self.assertFalse(LessonMark.objects.filter(lesson=self.lesson).exists())
        self.assertEqual(self.lesson.hours, gradebook.DEFAULT_LESSON_HOURS)
