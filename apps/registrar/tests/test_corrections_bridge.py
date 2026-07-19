"""Tests: journal corrections (excused absence / documented fixes) + exam↔journal bridge."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import corrections, exam_bridge, gradebook, services
from apps.registrar.models import (
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    Curriculum,
    CurriculumSubject,
    JournalCorrection,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _pdf(name="doc.pdf"):
    # %PDF magic bytes so core.upload_security signature sniffing accepts it.
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class _BaseJournalSetup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("cx_owner", "cx_owner@qku.edu.az", "pw")
        self.admin = User.objects.create_user("cx_admin", "cx_admin@qku.edu.az", "pw", is_superuser=True)
        self.admin.first_name = "Aygün"
        self.admin.last_name = "Registrar"
        self.admin.save(update_fields=["first_name", "last_name"])
        with bypass_rls():
            self.org = Organization.objects.create(
                name="CX Univ",
                slug="cx-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="cx-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
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
            self.teacher = User.objects.create_user("cx_teacher", "cx_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("cx_student", "cx_student@qku.edu.az", "pw")
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.lesson_hours = 60  # allowed absence = 15h
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()

    def _absent_lesson(self, day, hours=8):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 10, day),
                kind=LessonKind.LECTURE,
            )
            lesson.hours = hours
            lesson.save(update_fields=["hours"])
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.ABSENT,
            )
        return lesson, mark

    def _seminar_mark(self, day, score):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 10, day),
                kind=LessonKind.SEMINAR,
            )
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
                score=Decimal(score),
            )
        return lesson, mark


class CorrectionServiceTest(_BaseJournalSetup):
    def test_excused_absence_removes_it_from_the_limit(self):
        _lesson, mark = self._absent_lesson(1, hours=8)
        with bypass_rls():
            gradebook.recompute_absence_hours(enrollment=self.enrollment)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 8)

        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.ATTENDANCE,
                new_status=AttendanceStatus.EXCUSED,
                reason=CorrectionReason.MEDICAL,
                note="Xəstəlik vərəqəsi",
                document=_pdf(),
                by_user=self.admin,
            )
        mark.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(mark.status, AttendanceStatus.EXCUSED)
        self.assertEqual(self.enrollment.absence_hours, 0)  # excused not counted

    def test_correction_requires_note_and_document(self):
        _lesson, mark = self._seminar_mark(2, 3)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                corrections.apply_correction(
                    mark=mark,
                    field=CorrectionField.SCORE,
                    new_score=9,
                    reason=CorrectionReason.TECHNICAL,
                    note="",
                    document=_pdf(),
                    by_user=self.admin,
                )
            with self.assertRaises(ValidationError):
                corrections.apply_correction(
                    mark=mark,
                    field=CorrectionField.SCORE,
                    new_score=9,
                    reason=CorrectionReason.TECHNICAL,
                    note="düzəliş",
                    document=None,
                    by_user=self.admin,
                )

    def test_score_correction_is_whole_number_and_recorded(self):
        _lesson, mark = self._seminar_mark(3, 3)
        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.APPEAL,
                note="Apellyasiya qərarı",
                document=_pdf(),
                by_user=self.admin,
            )
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("9"))
        c = JournalCorrection.objects.get(lesson_mark=mark)
        self.assertEqual(c.old_score, 3)
        self.assertEqual(c.new_score, 9)
        self.assertEqual(c.corrected_by_name, "Aygün Registrar")  # from profile, not typed

    def test_float_score_rejected(self):
        _lesson, mark = self._seminar_mark(4, 3)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                corrections.apply_correction(
                    mark=mark,
                    field=CorrectionField.SCORE,
                    new_score="5.5",
                    reason=CorrectionReason.TECHNICAL,
                    note="x",
                    document=_pdf(),
                    by_user=self.admin,
                )

    def test_corrected_cell_is_locked_from_teacher_bulk_save(self):
        lesson, mark = self._seminar_mark(5, 3)
        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.APPEAL,
                note="qərar",
                document=_pdf(),
                by_user=self.admin,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                by_user=self.teacher,
                entries=[
                    {
                        "lesson_id": str(lesson.id),
                        "enrollment_id": str(self.enrollment.id),
                        "status": AttendanceStatus.PRESENT,
                        "score": 2,
                    }
                ],
            )
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("9"))  # unchanged — correction protected

    def test_correction_map_annotates_cell(self):
        _lesson, mark = self._seminar_mark(6, 3)
        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.APPEAL,
                note="qeyd",
                document=_pdf(),
                by_user=self.admin,
            )
            cmap = corrections.corrections_map_for_offering(self.offering)
        self.assertIn(str(mark.id), cmap)
        self.assertEqual(cmap[str(mark.id)][0]["new"], 9)


class ExamBridgeTest(_BaseJournalSetup):
    def _give_entry(self, points):
        with bypass_rls():
            remaining, day = int(points), 10
            while remaining > 0:
                chunk = min(10, remaining)
                self._seminar_mark(day, chunk)
                remaining -= chunk
                day += 1

    def test_resolve_enrollment_by_subject(self):
        with bypass_rls():
            e = exam_bridge.resolve_enrollment(student=self.student, subject_id=self.subject.id, organization=self.org)
        self.assertEqual(e, self.enrollment)

    def test_eligibility_barred_by_absence(self):
        self._absent_lesson(1, hours=20)  # > 15h allowed
        with bypass_rls():
            gradebook.recompute_absence_hours(enrollment=self.enrollment)
            elig = exam_bridge.exam_eligibility(student=self.student, subject_id=self.subject.id, organization=self.org)
        self.assertTrue(elig["linked"])
        self.assertTrue(elig["barred"])
        self.assertIn("%", elig["reason"])

    def test_record_exam_result_scales_to_50_whole_number(self):
        self._give_entry(30)
        with bypass_rls():
            # 85% of a 50-point exam scale → 43 (whole number, half-up)
            fg = exam_bridge.record_exam_result(
                student=self.student,
                subject_id=self.subject.id,
                organization=self.org,
                score_percent=85,
                by_user=self.admin,
            )
        self.assertIsNotNone(fg)
        self.assertEqual(fg.exam_score, Decimal("43"))

    def test_expelled_gets_zero_then_fails(self):
        self._give_entry(40)
        with bypass_rls():
            exam_bridge.record_exam_result(
                student=self.student,
                subject_id=self.subject.id,
                organization=self.org,
                score_percent=95,
                is_expelled=True,
                by_user=self.admin,
            )
            summary = exam_bridge.exam_result_summary(
                student=self.student, subject_id=self.subject.id, organization=self.org
            )
        self.assertEqual(summary["exam_score"], Decimal("0"))
        self.assertEqual(summary["letter"], "F")
        self.assertTrue(summary["failed"])

    def test_letter_grade_from_entry_plus_exam(self):
        self._give_entry(40)  # entry 40
        with bypass_rls():
            exam_bridge.record_exam_result(
                student=self.student,
                subject_id=self.subject.id,
                organization=self.org,
                score_percent=80,  # 80% * 50 = 40 → total 80 → "B" (81 threshold? 80 → C)
                by_user=self.admin,
            )
            summary = exam_bridge.exam_result_summary(
                student=self.student, subject_id=self.subject.id, organization=self.org
            )
        # total = 40 + 40 = 80 → band: >=71 "C" (default bands 91A/81B/71C/61D/51E)
        self.assertEqual(summary["total"], Decimal("80"))
        self.assertEqual(summary["letter"], "C")
        self.assertTrue(summary["passed"])

    def test_unlinked_exam_is_noop(self):
        with bypass_rls():
            fg = exam_bridge.record_exam_result(
                student=self.student,
                subject_id=None,
                organization=self.org,
                score_percent=90,
            )
        self.assertIsNone(fg)


class StudentJournalFazaBTest(_BaseJournalSetup):
    def _ctx(self, **params):
        from django.test import RequestFactory

        from apps.registrar.public import build_student_journal_context

        req = RequestFactory().get("/", params)
        req.user = self.student
        with bypass_rls():
            return build_student_journal_context(req, organization=self.org)["journal_student_section"]

    def test_no_subject_shows_cards_not_detail(self):
        self._seminar_mark(3, 7)
        sec = self._ctx()  # no ?subject → cards landing
        self.assertIsNone(sec["detail"])
        self.assertTrue(sec["subjects"])
        self.assertIn("teacher", sec["subjects"][0])
        self.assertEqual(sec["subjects"][0]["teacher"], self.teacher)
        self.assertTrue(sec["semester_options"])  # semester picker

    def test_subject_selected_shows_detail_with_kinds(self):
        self._seminar_mark(3, 7)
        self._absent_lesson(4, hours=2)
        sec = self._ctx(subject=str(self.enrollment.id))
        self.assertIsNotNone(sec["detail"])
        self.assertEqual(sec["detail"]["teacher"], self.teacher)
        kinds = {k["value"] for k in sec["detail"]["lesson_kinds"]}
        self.assertTrue(kinds)  # lesson-type filter options present
        # history rows carry kind for the type column + filter
        self.assertTrue(all("kind" in h for h in sec["detail"]["history"]))


class CorrectionMediaAccessTest(_BaseJournalSetup):
    def test_pdf_denied_to_unrelated_user_allowed_to_owner(self):
        from core.media_views import _check_journal_correction_access

        _lesson, mark = self._seminar_mark(8, 3)
        with bypass_rls():
            c = corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.MEDICAL,
                note="arayış",
                document=_pdf(),
                by_user=self.admin,
            )
            path = c.document.name
            # Owning student may read their own justification document.
            self.assertTrue(_check_journal_correction_access(self.student, path))
            # An unrelated non-admin (the teacher) is denied.
            self.assertFalse(_check_journal_correction_access(self.teacher, path))


class CorrectionViewTest(_BaseJournalSetup):
    def _login_corrector(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_non_corrector_cannot_open_correction_list(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = self.client.get("/jurnal/duzelis/")
        self.assertEqual(resp.status_code, 404)

    def test_corrector_opens_correction_list_and_journal(self):
        self._login_corrector()
        resp = self.client.get("/jurnal/duzelis/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.subject.name)
        resp2 = self.client.get(f"/jurnal/duzelis/{self.offering.id}/")
        self.assertEqual(resp2.status_code, 200)

    def test_apply_endpoint_records_correction(self):
        _lesson, mark = self._seminar_mark(7, 3)
        self._login_corrector()
        resp = self.client.post(
            f"/jurnal/duzelis/{self.offering.id}/tetbiq/",
            data={
                "mark_id": str(mark.id),
                "field": "score",
                "new_score": "8",
                "reason": CorrectionReason.APPEAL,
                "note": "Apellyasiya qərarı",
                "document": _pdf(),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("8"))
        self.assertTrue(JournalCorrection.objects.filter(lesson_mark=mark).exists())
