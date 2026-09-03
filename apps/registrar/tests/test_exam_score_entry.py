"""İmtahan Mərkəzi — kağız imtahan balının əl ilə daxil edilməsi (servis qatı).

Sahibin qərarı (2026-08): yazılı/praktiki imtahan kağız üzərində keçir, balları
sonradan İmtahan Mərkəzi sistemə köçürür. Burada yoxlanan müqavilə:

* qrup (açılış) seçimi düzgün tələbələri gətirir;
* bal ``FinalGrade.exam_score``-a düşür və yekun (giriş + çıxış) düzgün olur;
* KİLİDLİ jurnalda imtahan balı YAZILIR (əsas regresiya, E5);
* təkrar daxiletmə idempotentdir;
* sonrakı dəyişiklik sənədsiz RƏDD, sənədlə keçir (E7);
* sübut faylı saxlanılır və audit izində görünür.
"""

import datetime
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import exam_score_entry as service
from apps.registrar import finals, gradebook, services
from apps.registrar.models import (
    ApprovalStatus,
    CorrectionReason,
    Curriculum,
    CurriculumSubject,
    ExamScoreEntry,
    ExamScoreEntryKind,
    FinalGrade,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_MEDIA = tempfile.mkdtemp(prefix="ese-media-")


def _pdf(name="verq.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


def _jpg(name="verq.jpg"):
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0abc", content_type="image/jpeg")


@override_settings(MEDIA_ROOT=_MEDIA)
class ExamScoreEntryServiceTest(TestCase):
    """İki qruplu bir fənn — qrup seçiminin düzgünlüyü də yoxlanılır."""

    def setUp(self):
        self.owner = User.objects.create_user("ese_owner", "ese_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="ESE Univ",
                slug="ese-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group_a = OrgUnit.objects.create(
                organization=self.org, name="A-qrup", slug="ese-a", unit_type=OrgUnitType.GROUP
            )
            self.group_b = OrgUnit.objects.create(
                organization=self.org, name="B-qrup", slug="ese-b", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.teacher = User.objects.create_user("ese_teacher", "ese_teacher@qku.edu.az", "pw")
            self.center = User.objects.create_user("ese_center", "ese_center@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.center,
                organization=self.org,
                role=self.org.roles.get(name="exam_center"),
                is_primary=True,
                is_active=True,
            )
            self.students = {}
            for key, group in (("a1", self.group_a), ("a2", self.group_a), ("b1", self.group_b)):
                student = User.objects.create_user(f"ese_{key}", f"ese_{key}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=self.org,
                    role=self.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                record = StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=group,
                    admission_year=2024,
                )
                services.enroll_mandatory_subjects(record=record, period=self.period, semester_number=1)
                self.students[key] = student

            self.enrollment_a1 = self.students["a1"].enrollments.get()
            self.offering_a = self.enrollment_a1.offering
            self.offering_b = self.students["b1"].enrollments.get().offering
            for offering in (self.offering_a, self.offering_b):
                offering.lesson_hours = 60
                offering.instructor = self.teacher
                offering.save(update_fields=["lesson_hours", "instructor"])

    # ── köməkçilər ───────────────────────────────────────────────────────────
    def _set_entry(self, enrollment, points):
        """Seminar balları ilə giriş balı ver (hər dərs ≤ 10)."""
        remaining, day = int(points), 1
        while remaining > 0:
            chunk = min(10, remaining)
            seminar = gradebook.create_lesson(
                allow_past=True,
                offering=enrollment.offering,
                date=datetime.date(2024, 10, day),
                kind=LessonKind.SEMINAR,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=enrollment.offering,
                entries=[
                    {"lesson_id": seminar.id, "enrollment_id": enrollment.id, "status": "present", "score": chunk}
                ],
                by_user=self.teacher,
            )
            remaining -= chunk
            day += 1

    def _close_journal(self, offering):
        scheme = gradebook.ensure_assessment_scheme(offering=offering)
        scheme.approval_status = ApprovalStatus.APPROVED
        scheme.is_published = True
        scheme.save(update_fields=["approval_status", "is_published"])

    # ── icazə ────────────────────────────────────────────────────────────────
    def test_exam_center_can_enter_teacher_cannot(self):
        with bypass_rls():
            self.assertTrue(service.can_enter_exam_scores(self.center, self.org))
            self.assertFalse(service.can_enter_exam_scores(self.teacher, self.org))

    # ── qrup seçimi ──────────────────────────────────────────────────────────
    def test_group_selection_returns_only_its_students(self):
        with bypass_rls():
            offerings = service.offerings_for_subject(
                organization=self.org, period=self.period, subject_id=self.subject.id
            )
            self.assertEqual(len(offerings), 2)

            roster_a = service.roster_for_offering(offering=self.offering_a)
            usernames = {row["student"].username for row in roster_a["rows"]}
            self.assertEqual(usernames, {"ese_a1", "ese_a2"})

            roster_b = service.roster_for_offering(offering=self.offering_b)
            self.assertEqual({row["student"].username for row in roster_b["rows"]}, {"ese_b1"})

    # ── bal FinalGrade-ə düşür, yekun düzgün ─────────────────────────────────
    def test_score_lands_in_final_grade_and_total(self):
        with bypass_rls():
            self._set_entry(self.enrollment_a1, 40)
            entry = service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)

            self.assertIsNotNone(entry)
            self.assertEqual(entry.kind, ExamScoreEntryKind.INITIAL)
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("45"))

            result = finals.compute_final_result(enrollment=self.enrollment_a1)
            self.assertEqual(result["entry_score"], Decimal("40"))
            self.assertEqual(result["exam_score"], Decimal("45"))
            self.assertEqual(result["total"], Decimal("85"))
            self.assertTrue(result["passed"])

    def test_score_above_cap_is_rejected(self):
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(enrollment=self.enrollment_a1, score="90", by_user=self.center)

    def test_fractional_score_is_rejected(self):
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(enrollment=self.enrollment_a1, score="41.5", by_user=self.center)

    # ── ƏSAS REGRESİYA: kilidli jurnal ───────────────────────────────────────
    def test_closed_journal_still_accepts_exam_score(self):
        """Jurnal semestr sonunda bağlanır, imtahan ondan SONRA keçir (E5)."""
        with bypass_rls():
            self._set_entry(self.enrollment_a1, 40)
            self._close_journal(self.offering_a)
            self.assertTrue(gradebook.journal_is_locked(self.offering_a))

            entry = service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)

            self.assertIsNotNone(entry)
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("45"))
            self.assertEqual(finals.compute_final_result(enrollment=self.enrollment_a1)["total"], Decimal("85"))

    # ── idempotentlik ────────────────────────────────────────────────────────
    def test_repeat_same_score_is_idempotent(self):
        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            repeat = service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)

            self.assertIsNone(repeat)  # dəyişiklik yoxdur
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment_a1).count(), 1)
            self.assertEqual(FinalGrade.objects.filter(enrollment=self.enrollment_a1).count(), 1)

    def test_blank_score_leaves_existing_value_untouched(self):
        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            self.assertIsNone(service.record_exam_score(enrollment=self.enrollment_a1, score="", by_user=self.center))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("45"))

    # ── sonrakı dəyişiklik = təqdimatlı (E7) ─────────────────────────────────
    def test_change_without_document_is_rejected(self):
        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)

            with self.assertRaises(ValidationError):  # səbəb/qeyd/sənəd yoxdur
                service.record_exam_score(enrollment=self.enrollment_a1, score="30", by_user=self.center)
            with self.assertRaises(ValidationError):  # sənəd yoxdur
                service.record_exam_score(
                    enrollment=self.enrollment_a1,
                    score="30",
                    by_user=self.center,
                    reason=CorrectionReason.TECHNICAL,
                    note="Vərəq yenidən yoxlanıldı",
                )
            # bal DƏYİŞMƏYİB
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("45"))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment_a1).count(), 1)

    def test_change_with_document_is_accepted_and_audited(self):
        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            entry = service.record_exam_score(
                enrollment=self.enrollment_a1,
                score="30",
                by_user=self.center,
                reason=CorrectionReason.APPEAL,
                note="Apellyasiya qərarı ilə düzəliş",
                evidence=_pdf(),
            )

            self.assertEqual(entry.kind, ExamScoreEntryKind.CORRECTION)
            self.assertEqual(entry.old_score, Decimal("45"))
            self.assertEqual(entry.new_score, Decimal("30"))
            self.assertTrue(entry.evidence)  # sübut saxlanıldı
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("30"))
            self.assertTrue(
                AuditLog.objects.filter(resource_type="registrar.exam_score_entry", resource_id=str(entry.pk)).exists()
            )

    # ── sübut (şəkil) ilkin daxiletmədə FAKULTATİVdir ────────────────────────
    def test_initial_entry_accepts_optional_image_evidence(self):
        with bypass_rls():
            entry = service.record_exam_score(
                enrollment=self.enrollment_a1,
                score="40",
                by_user=self.center,
                note="İmtahan vərəqinin şəkli",
                evidence=_jpg(),
            )
            self.assertEqual(entry.kind, ExamScoreEntryKind.INITIAL)
            self.assertTrue(entry.evidence.name.endswith(".jpg"))
            self.assertIn("verq", entry.evidence.name)

    def test_evidence_rejects_unsupported_type(self):
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(
                    enrollment=self.enrollment_a1,
                    score="40",
                    by_user=self.center,
                    evidence=SimpleUploadedFile("x.txt", b"salam", content_type="text/plain"),
                )
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment_a1).exists())

    # ── toplu yazı ───────────────────────────────────────────────────────────
    def test_bulk_save_writes_rows_and_collects_errors(self):
        with bypass_rls():
            enrollment_a2 = self.students["a2"].enrollments.get()
            service.record_exam_score(enrollment=enrollment_a2, score="20", by_user=self.center)

            result = service.save_roster_scores(
                offering=self.offering_a,
                rows=[
                    {"enrollment_id": str(self.enrollment_a1.id), "score": "35"},
                    {"enrollment_id": str(enrollment_a2.id), "score": "44"},  # sənədsiz DƏYİŞİKLİK
                ],
                by_user=self.center,
            )

            self.assertEqual(result["written"], 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("35"))
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment_a2).exam_score, Decimal("20"))

    # ── audit izində mənbə qeydi ─────────────────────────────────────────────
    def test_grade_history_marks_manual_exam_centre_source(self):
        from apps.registrar import grade_audit

        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            history = grade_audit.get_grade_history(offering=self.offering_a)
            blob = str(history)
            self.assertIn("imtahan mərkəzi · əl ilə", blob)

    # ── çox cəhd: sonuncu rəsmi, əvvəlkilər görünür (M1/M2) ──────────────────
    def _make_attempt(self, student, *, correct, wrong, minutes):
        import datetime as _dt

        from django.utils import timezone

        from apps.exams.models import Exam, ExamAttempt

        start = timezone.now() - _dt.timedelta(minutes=minutes)
        exam = Exam.objects.create(
            organization=self.org,
            author=self.teacher,
            title="Yazılı imtahan",
            exam_type="written",
            subject=self.subject,
            start_datetime=start,
            end_datetime=start + _dt.timedelta(hours=1),
            is_active=True,
        )
        attempt = ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
            correct_count=correct,
            wrong_count=wrong,
        )
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=start, finished_at=start)
        return attempt

    def test_attempt_history_marks_last_as_official(self):
        from apps.registrar import exam_attempt_history

        with bypass_rls():
            self._make_attempt(self.students["a1"], correct=8, wrong=2, minutes=120)  # 80%
            self._make_attempt(self.students["a1"], correct=65, wrong=35, minutes=30)  # 65%

            rows = exam_attempt_history.attempt_rows_for_enrollment(self.enrollment_a1)

            self.assertEqual([r["percent"] for r in rows], [80.0, 65.0])
            self.assertEqual([r["is_official"] for r in rows], [False, True])
            self.assertEqual([r["label"] for r in rows], ["1-ci", "2-ci"])

    def test_roster_exposes_attempt_history(self):
        with bypass_rls():
            self._make_attempt(self.students["a1"], correct=8, wrong=2, minutes=120)
            self._make_attempt(self.students["a1"], correct=65, wrong=35, minutes=30)

            roster = service.roster_for_offering(offering=self.offering_a)
            row = next(r for r in roster["rows"] if r["student"].username == "ese_a1")

            self.assertEqual(len(row["attempts"]), 2)
            self.assertTrue(row["attempts"][-1]["is_official"])
            self.assertFalse(row["attempts"][0]["is_official"])

    def test_trial_and_unfinished_attempts_are_ignored(self):
        from apps.exams.models import ExamAttempt
        from apps.registrar import exam_attempt_history

        with bypass_rls():
            attempt = self._make_attempt(self.students["a1"], correct=8, wrong=2, minutes=120)
            ExamAttempt.objects.filter(pk=attempt.pk).update(is_trial=True)
            self.assertEqual(exam_attempt_history.attempt_rows_for_enrollment(self.enrollment_a1), [])


class ExamScoreEntryNarrowedPermissionTests(TestCase):
    """Sahibin qərarı (2026-08-28): «Daralt — ancaq imtahan mərkəzi imtahan final
    balını yaza bilsin; müəllim və digərləri yaza bilməsin.»

    Açar QƏSDƏN ``final_score.`` prefiksindədir: ``exam.*`` wildcard-ı onu ƏHATƏ
    ETMİR, ona görə dekan/kafedra müdiri/prorektor/müəllim onu avtomatik almır.
    """

    def test_exam_wildcard_does_not_grant_final_score_entry(self):
        from apps.registrar.exam_score_entry import ENTRY_PERMISSION
        from core.permissions import has_permission

        # `exam.*` daşıyan rol (dekan, kafedra müdiri, prorektor…) ALMIR.
        self.assertFalse(has_permission(["exam.*"], ENTRY_PERMISSION))
        self.assertFalse(has_permission(["exam.view", "exam.create", "exam.manage"], ENTRY_PERMISSION))
        # Açıq verilmiş açar və org-sahibi ulduzu İŞLƏYİR.
        self.assertTrue(has_permission([ENTRY_PERMISSION], ENTRY_PERMISSION))
        self.assertTrue(has_permission(["*"], ENTRY_PERMISSION))

    def test_default_roles_grant_it_only_to_the_exam_centre(self):
        from apps.organizations.default_roles import get_default_roles_for_org_type
        from apps.registrar.exam_score_entry import ENTRY_PERMISSION
        from core.constants import OrganizationType
        from core.permissions import has_permission

        holders = set()
        for role in get_default_roles_for_org_type(OrganizationType.UNIVERSITY):
            if has_permission(list(role["permissions"]), ENTRY_PERMISSION):
                holders.add(role["name"])

        # Rektor `*` ilə əhatə olunur; qalanlar YALNIZ imtahan mərkəzinin qərar rollarıdır.
        self.assertEqual(holders - {"rector"}, {"exam_center", "exam_center_head"})
        for denied in ("teacher", "dean", "chair_head", "vice_rector", "ikt_rehber", "exam_center_staff"):
            self.assertNotIn(denied, holders, f"{denied} yekun imtahan balını yaza bilməməlidir")
