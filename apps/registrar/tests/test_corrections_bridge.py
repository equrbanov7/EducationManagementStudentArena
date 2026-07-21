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
    LessonCorrection,
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

    def test_revert_last_grade_correction_restores_previous_value(self):
        # Səhvən edilmiş düzəlişi geri al → xana köhnə (müəllim) dəyərinə qayıdır,
        # sarı işarə (JournalCorrection) itir.
        _lesson, mark = self._seminar_mark(11, 3)
        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.APPEAL,
                note="Səhv düzəliş",
                document=_pdf(),
                by_user=self.admin,
            )
            mark.refresh_from_db()
            self.assertEqual(mark.score, Decimal("9"))
            ok = corrections.revert_last_grade_correction(mark=mark, by_user=self.admin)
            self.assertTrue(ok)
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("3"))  # köhnə dəyər qayıtdı
        self.assertFalse(JournalCorrection.objects.filter(lesson_mark=mark).exists())  # sarı getdi

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
        # Term picker = academic-year + season (Payız/Yaz/Yay), NOT semester 1-10.
        self.assertTrue(sec["year_choices"])
        self.assertTrue(sec["period_choices"])
        self.assertEqual(sec["selected_period_id"], str(self.period.id))

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


class JournalSummaryQueryCountTest(_BaseJournalSetup):
    def _add_second_subject_with_marks(self):
        from apps.registrar.models import CurriculumSubject, LessonKind, Subject

        with bypass_rls():
            subj2 = Subject.objects.create(organization=self.org, code="CS102", name="Alqoritmlər")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=subj2, semester_number=1
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            off2 = self.student.enrollments.filter(offering__subject=subj2).first().offering
            off2.lesson_hours = 60
            off2.save(update_fields=["lesson_hours"])
            for d in (11, 12, 13):
                lesson = gradebook.create_lesson(
                    allow_past=True, offering=off2, date=datetime.date(2024, 10, d), kind=LessonKind.SEMINAR
                )
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=off2.enrollments.get(student=self.student),
                    status=AttendanceStatus.PRESENT,
                    score=Decimal(6),
                )

    def test_summary_query_count_does_not_scale_with_subjects(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._seminar_mark(3, 7)  # marks on subject 1
        # 1 subject
        with bypass_rls():
            with CaptureQueriesContext(connection) as ctx1:
                gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
        q1 = len(ctx1.captured_queries)

        self._add_second_subject_with_marks()  # now 2 subjects
        with bypass_rls():
            with CaptureQueriesContext(connection) as ctx2:
                gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
        q2 = len(ctx2.captured_queries)

        # Batched: adding a subject must NOT add per-subject queries (N+1 gone).
        # Allow a tiny margin; without batching this delta was ~4-5 per subject.
        self.assertLessEqual(q2 - q1, 1, f"journal summary N+1: 1-subj={q1}q, 2-subj={q2}q")


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

    def test_corrector_correction_urls_redirect_in_place(self):
        # Ayrı düzəliş səhifələri ləğv edildi → jurnal siyahısına / yerində düzəliş
        # rejiminə (journal_detail ?correct=1) yönləndirir.
        self._login_corrector()
        resp = self.client.get("/jurnal/duzelis/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.endswith("/jurnal/"))
        resp2 = self.client.get(f"/jurnal/duzelis/{self.offering.id}/")
        self.assertEqual(resp2.status_code, 302)
        self.assertIn("?correct=1", resp2.url)

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

    def test_delete_endpoint_reverts_correction(self):
        _lesson, mark = self._seminar_mark(9, 4)
        with bypass_rls():
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=10,
                reason=CorrectionReason.TECHNICAL,
                note="Səhv",
                document=_pdf(),
                by_user=self.admin,
            )
        self._login_corrector()
        resp = self.client.post(
            f"/jurnal/duzelis/{self.offering.id}/sil/",
            data={"type": "grade", "mark_id": str(mark.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("4"))
        self.assertFalse(JournalCorrection.objects.filter(lesson_mark=mark).exists())


class LessonCorrectionServiceTest(_BaseJournalSetup):
    """#5/#6 — İKT dərs tarixi/tipi/saatı dəyişəndə sənədli, audited düzəliş."""

    def test_requires_document(self):
        lesson, _mark = self._absent_lesson(3)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                corrections.apply_lesson_correction(
                    lesson=lesson,
                    new_date="2024-10-05",
                    reason=CorrectionReason.TECHNICAL,
                    note="Səhv tarix",
                    document=None,
                    by_user=self.admin,
                )

    def test_changes_date_and_kind_and_records_snapshot(self):
        lesson, _mark = self._absent_lesson(3)  # LECTURE, 2024-10-03
        with bypass_rls():
            corr = corrections.apply_lesson_correction(
                lesson=lesson,
                new_date="2024-10-09",
                new_kind=LessonKind.SEMINAR,
                reason=CorrectionReason.TECHNICAL,
                note="Mühazirə/seminar qarışıb + tarix səhv",
                document=_pdf(),
                by_user=self.admin,
            )
        lesson.refresh_from_db()
        self.assertEqual(lesson.date, datetime.date(2024, 10, 9))
        self.assertEqual(lesson.kind, LessonKind.SEMINAR)
        self.assertEqual(corr.old_kind, LessonKind.LECTURE)
        self.assertEqual(corr.new_kind, LessonKind.SEMINAR)
        self.assertEqual(corr.old_date, datetime.date(2024, 10, 3))
        self.assertEqual(corr.corrected_by_name, "Aygün Registrar")
        self.assertTrue(LessonCorrection.objects.filter(lesson=lesson).exists())

    def test_no_change_rejected(self):
        lesson, _mark = self._absent_lesson(3)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                corrections.apply_lesson_correction(
                    lesson=lesson,
                    new_date="2024-10-03",
                    new_kind=LessonKind.LECTURE,
                    reason=CorrectionReason.TECHNICAL,
                    note="Dəyişiklik yoxdur",
                    document=_pdf(),
                    by_user=self.admin,
                )


class ItemCorrectionTest(_BaseJournalSetup):
    """E) Sərbəst iş + kurs işi sənədli düzəliş (bal xanası ilə eyni prosedur) + geri alma."""

    def test_selfwork_correction_applies_reverts_and_requires_doc(self):
        from apps.registrar import item_corrections, journal_extras
        from apps.registrar.models import SelfWorkCorrection, SelfWorkMark

        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="SW1")
            # Sənədsiz → rədd.
            with self.assertRaises(ValidationError):
                item_corrections.apply_selfwork_correction(
                    offering=self.offering,
                    topic=topic,
                    enrollment=self.enrollment,
                    new_done=True,
                    reason=CorrectionReason.TECHNICAL,
                    note="x",
                    document=None,
                    by_user=self.admin,
                )
            corr = item_corrections.apply_selfwork_correction(
                offering=self.offering,
                topic=topic,
                enrollment=self.enrollment,
                new_done=True,
                reason=CorrectionReason.TECHNICAL,
                note="Səhv",
                document=_pdf(),
                by_user=self.admin,
            )
            self.assertTrue(SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment).done)
            self.assertEqual(corr.old_done, False)
            self.assertEqual(corr.new_done, True)
            cmap = item_corrections.selfwork_corrections_map(self.offering)
            self.assertIn(f"{topic.id}:{self.enrollment.id}", cmap)
            # Geri al → təhvil 0-a qayıdır, correction itir (sarı gedir).
            self.assertTrue(
                item_corrections.revert_last_selfwork_correction(
                    topic=topic, enrollment=self.enrollment, by_user=self.admin
                )
            )
            self.assertFalse(SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment).done)
            self.assertFalse(SelfWorkCorrection.objects.filter(topic=topic, enrollment=self.enrollment).exists())

    def test_coursework_correction_applies_and_reverts(self):
        from decimal import Decimal as D

        from apps.registrar import item_corrections, journal_extras
        from apps.registrar.models import CourseWork, CourseWorkCorrection

        with bypass_rls():
            journal_extras.save_course_work(
                enrollment=self.enrollment,
                topic="İlk",
                score="50",
                submitted_on=datetime.date(2024, 10, 1),
                by_user=self.teacher,
            )
            corr = item_corrections.apply_coursework_correction(
                enrollment=self.enrollment,
                new_score="88",
                new_topic="Düzəliş",
                new_date=None,
                reason=CorrectionReason.APPEAL,
                note="Apellyasiya",
                document=_pdf(),
                by_user=self.admin,
            )
            self.assertEqual(CourseWork.objects.get(enrollment=self.enrollment).score, D("88"))
            self.assertEqual(corr.old_score, D("50"))
            self.assertEqual(corr.new_score, D("88"))
            self.assertTrue(
                item_corrections.revert_last_coursework_correction(enrollment=self.enrollment, by_user=self.admin)
            )
            self.assertEqual(CourseWork.objects.get(enrollment=self.enrollment).score, D("50"))
            self.assertFalse(CourseWorkCorrection.objects.filter(enrollment=self.enrollment).exists())
