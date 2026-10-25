"""«İmtahan balının daxil edilməsi» — midterm / final, sütun cəmi, 15 dəqiqə, apellyasiya, RİM, tələbəyə gecikmə.

Sahibin tələbi (2026-10-25): midterm maks 30 / final maks 50; sütunların maks cəmi HƏMİŞƏ tavandır; təsdiqdən
sonra 15 dəqiqə daxil edən dəyişə bilər, sonra yalnız RİM (təqdimat) və ya apellyasiya (sənəd məcburi);
nəticə tələbəyə 1 gün sonra görünür; defolt imtahan semestr təqvimindən.
"""

from __future__ import annotations

import datetime
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import exam_score_assessment as rules
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_release as release
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import interim_components, services, transcript
from apps.registrar.models import (
    ComponentScore,
    CorrectionReason,
    Curriculum,
    CurriculumSubject,
    ExamAssessment,
    ExamScoreEntry,
    ExamScoreEntryKind,
    FinalGrade,
    KollokviumWindow,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
_MEDIA = tempfile.mkdtemp(prefix="ese-assess-media-")


def _pdf(name="apellyasiya.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class MidtermPeriodFixture:
    """2026/2027 Payız (Midterm rejimi) — bir qrup, bir fənn, iki tələbə; İM rəhbəri, İM işçisi, RİM rəhbəri."""

    @classmethod
    def build_fixture(cls, prefix="esa"):
        cls.owner = User.objects.create_user(f"{prefix}_owner", f"{prefix}_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name=f"{prefix.upper()} Univ",
            slug=f"{prefix}-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.group = OrgUnit.objects.create(
            organization=cls.org, name=f"{prefix.upper()}-101", slug=f"{prefix}-g1", unit_type=OrgUnitType.GROUP
        )
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="2026/2027 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=datetime.date(2026, 9, 15),
            end_date=datetime.date(2027, 1, 31),
            is_current=True,
        )
        program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
        subject = Subject.objects.create(organization=cls.org, code="CS201", name="Alqoritmlər")
        CurriculumSubject.objects.create(
            organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
        )
        cls.center = cls._member(f"{prefix}_center", "exam_center_head")
        cls.staff = cls._member(f"{prefix}_staff", "exam_center_staff")
        cls.rim = cls._member(f"{prefix}_rim", "ikt_rehber")
        cls.teacher = cls._member(f"{prefix}_teacher", "teacher")
        cls.enrollments = []
        for index in (1, 2):
            student = cls._member(f"{prefix}_student{index}", "student")
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2026,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
            cls.enrollments.append(student.enrollments.get())
        cls.offering = cls.enrollments[0].offering
        cls.offering.instructor = cls.teacher
        cls.offering.lesson_hours = 60
        cls.offering.save(update_fields=["instructor", "lesson_hours"])

    @classmethod
    def _member(cls, username, role):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
        )
        return user


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class AssessmentRulesTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("esa")

    # ── sütun şəbəkəsi ───────────────────────────────────────────────────────
    def test_equal_split_uses_integers_and_puts_remainder_last(self):
        self.assertEqual(rules.equal_split(30, 4), [7, 7, 7, 9])
        self.assertEqual(rules.equal_split(30, 3), [10, 10, 10])
        self.assertEqual(rules.equal_split(50, 5), [10, 10, 10, 10, 10])
        self.assertEqual(rules.equal_split(50, 3), [16, 16, 18])
        self.assertEqual(sum(rules.equal_split(30, 7)), 30)

    def test_column_maxes_must_sum_exactly_to_cap(self):
        self.assertEqual(rules.clean_column_maxes("6,6,6,6,6", 30), [6, 6, 6, 6, 6])
        self.assertEqual(rules.clean_column_maxes([20, 30], 50), [20, 30])
        for raw in ("10,10", "10,10,11", "0,30", "31", "", "10,x,10", ",".join(["3"] * 11)):
            with self.assertRaises(ValidationError, msg=raw):
                rules.clean_column_maxes(raw, 30)

    def test_default_columns_three_for_midterm_five_for_final(self):
        self.assertEqual(rules.default_columns(rules.MIDTERM, 30), [10, 10, 10])
        self.assertEqual(rules.default_columns(rules.FINAL, 50), [10, 10, 10, 10, 10])

    def test_caps_are_30_and_50(self):
        with bypass_rls():
            self.assertEqual(rules.cap_for(self.offering, rules.MIDTERM), 30)
            self.assertEqual(rules.cap_for(self.offering, rules.FINAL), 50)

    # ── təqvimə görə defolt ──────────────────────────────────────────────────
    def test_default_assessment_follows_calendar(self):
        with bypass_rls():
            period = AcademicPeriod.objects.get(pk=self.period.pk)
            self.assertEqual(rules.default_assessment(period, today=datetime.date(2026, 11, 10)), rules.MIDTERM)
            self.assertEqual(rules.default_assessment(period, today=datetime.date(2027, 1, 25)), rules.FINAL)
            period.exam_session_start = datetime.date(2026, 12, 20)
            self.assertEqual(rules.default_assessment(period, today=datetime.date(2026, 12, 21)), rules.FINAL)
            KollokviumWindow.objects.create(
                organization=self.org,
                period=period,
                k_index=0,
                opens_on=datetime.date(2027, 1, 5),
                closes_on=datetime.date(2027, 1, 10),
                is_active=True,
            )
            period.exam_session_start = None
            # midterm pəncərəsi açıqdır → semestrin «final quyruğu» olsa belə midterm
            self.assertEqual(rules.default_assessment(period, today=datetime.date(2027, 1, 20)), rules.MIDTERM)
            old = AcademicPeriod(academic_year="2025/2026", start_date=datetime.date(2025, 9, 15))
            self.assertEqual(rules.default_assessment(old, today=datetime.date(2025, 11, 1)), rules.FINAL)

    # ── midterm yazısı → jurnalın «Midterm» xanası ─────────────────────────────
    def _midterm_sheet(self, user=None, evidence=None, maxes=(10, 10, 10)):
        return sheets.create_sheet(
            offering=self.offering,
            by_user=user or self.center,
            assessment=ExamAssessment.MIDTERM,
            question_maxes=list(maxes),
            evidence=evidence,
            checked_on=timezone.localdate(),
        )

    def test_midterm_lands_in_journal_midterm_cell_and_is_locked_for_teacher(self):
        enrollment = self.enrollments[0]
        with bypass_rls():
            sheet = self._midterm_sheet()
            result = service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(enrollment.pk), "question_scores": ["9", "8", "7"]}],
                by_user=self.center,
                sheet=sheet,
            )
            self.assertEqual(result["written"], 1, result)
            component = interim_components.ensure_kollokviums(self.offering)[0]
            cell = ComponentScore.objects.get(component=component, enrollment=enrollment)
            self.assertEqual(cell.score, Decimal("24"))
            self.assertEqual(cell.exam_source["source"], "paper_sheet")
            entry = ExamScoreEntry.objects.get(enrollment=enrollment)
            self.assertEqual(entry.assessment, ExamAssessment.MIDTERM)
            self.assertEqual(entry.question_scores, [9, 8, 7])
            self.assertFalse(FinalGrade.objects.filter(enrollment=enrollment, exam_score__isnull=False).exists())

    def test_midterm_column_and_total_caps_are_enforced(self):
        enrollment = self.enrollments[0]
        with bypass_rls():
            sheet = self._midterm_sheet(maxes=(5, 25))
            result = service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(enrollment.pk), "question_scores": ["6", "20"]}],  # S1 > 5
                by_user=self.center,
                sheet=sheet,
            )
            self.assertEqual(result["written"], 0)
            self.assertIn("S1", result["errors"][0][1])
            result = service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(enrollment.pk), "score": "31"}],  # tək bal > 30
                by_user=self.center,
                sheet=self._midterm_sheet(),
            )
            self.assertEqual(result["written"], 0)
        with self.assertRaises(ValidationError):
            sheets.sheet_metadata_from_post(
                {"assessment": "midterm", "question_maxes": "10,10,11"}, {}, offering=self.offering
            )

    # ── 15 dəqiqə / apellyasiya / RİM ────────────────────────────────────────
    def _final(self, score, user, *, kind="", evidence=None, reason="", note="", sheet_evidence=None):
        sheet = sheets.create_sheet(
            offering=self.offering,
            by_user=user,
            question_maxes=[50],
            evidence=sheet_evidence,
            checked_on=timezone.localdate(),
        )
        return service.save_roster_scores(
            offering=self.offering,
            rows=[
                {
                    "enrollment_id": str(self.enrollments[0].pk),
                    "question_scores": [score],
                    "kind": kind,
                    "reason": reason,
                    "note": note,
                    "evidence": evidence,
                }
            ],
            by_user=user,
            sheet=sheet,
        )

    def _score(self):
        return FinalGrade.objects.get(enrollment=self.enrollments[0]).exam_score

    def test_entering_user_can_change_within_window_without_document(self):
        with bypass_rls():
            self._final("40", self.center)
            result = self._final("42", self.center)
            self.assertEqual(result["written"], 1, result)
            self.assertEqual(self._score(), Decimal("42"))
            kinds = list(ExamScoreEntry.objects.order_by("created_at").values_list("kind", flat=True))
            self.assertEqual(kinds, [ExamScoreEntryKind.INITIAL, ExamScoreEntryKind.WINDOW_EDIT])

    def test_other_user_and_closed_window_cannot_change(self):
        with bypass_rls():
            self._final("40", self.center)
            self.assertEqual(self._final("41", self.staff)["written"], 0)  # başqa İM işçisi
            later = timezone.now() + timedelta(minutes=16)
            with mock.patch("django.utils.timezone.now", return_value=later):
                result = self._final("41", self.center)
            self.assertEqual(result["written"], 0)
            self.assertIn("15", result["errors"][0][1])
            self.assertEqual(self._score(), Decimal("40"))

    def test_window_length_comes_from_runtime_setting(self):
        with bypass_rls():
            self._final("40", self.center)
            later = timezone.now() + timedelta(minutes=16)
            with mock.patch("core.runtime_settings_exam_scores.edit_minutes", return_value=30):
                with mock.patch("django.utils.timezone.now", return_value=later):
                    self.assertEqual(self._final("41", self.center)["written"], 1)

    def test_appeal_after_window_requires_document_and_is_marked(self):
        with bypass_rls():
            self._final("40", self.center)
            later = timezone.now() + timedelta(minutes=16)
            with mock.patch("django.utils.timezone.now", return_value=later):
                # Sahib 2026-10-25: apellyasiya ilə dəyişiklik — YALNIZ İmtahan Mərkəzinin rəhbəri.
                staff = self._final("45", self.staff, kind="appeal", sheet_evidence=_pdf())
                self.assertEqual(staff["written"], 0)
                self.assertIn("rəhbəri", staff["errors"][0][1])
                no_doc = self._final("45", self.center, kind="appeal")
                self.assertEqual(no_doc["written"], 0)
                self.assertIn("apellyasiya sənədi", no_doc["errors"][0][1])
                ok = self._final("45", self.center, kind="appeal", sheet_evidence=_pdf())
            self.assertEqual(ok["written"], 1, ok)
            self.assertEqual(self._score(), Decimal("45"))
            appeal = ExamScoreEntry.objects.get(kind=ExamScoreEntryKind.APPEAL)
            self.assertEqual((appeal.old_score, appeal.new_score), (Decimal("40"), Decimal("45")))
            self.assertEqual(appeal.reason, CorrectionReason.APPEAL)
            self.assertEqual(appeal.entered_by, self.center)
            self.assertTrue(appeal.sheet.evidence)

    def test_rim_correction_only_for_rim_head_with_full_submission(self):
        with bypass_rls():
            self._final("40", self.center)
            later = timezone.now() + timedelta(minutes=16)
            submission = {"reason": CorrectionReason.TECHNICAL, "note": "Təqdimat №5", "evidence": _pdf()}
            with mock.patch("django.utils.timezone.now", return_value=later):
                denied = self._final("30", self.center, kind="correction", **submission)
                self.assertEqual(denied["written"], 0)
                self.assertIn("RİM", denied["errors"][0][1])
                no_note = self._final("30", self.rim, kind="correction", reason=CorrectionReason.TECHNICAL)
                self.assertEqual(no_note["written"], 0)
                ok = self._final("30", self.rim, kind="correction", **{**submission, "evidence": _pdf()})
            self.assertEqual(ok["written"], 1, ok)
            self.assertEqual(self._score(), Decimal("30"))
            self.assertTrue(ExamScoreEntry.objects.filter(kind=ExamScoreEntryKind.CORRECTION, entered_by=self.rim))

    # ── tələbəyə görünmə gecikməsi ───────────────────────────────────────────
    def _student_exam_score(self):
        data = transcript.build_student_own_transcript(student=self.enrollments[0].student, organization=self.org)
        rows = [row for sem in data["semesters"] for row in sem["rows"]]
        return rows[0]["result"]["exam_score"]

    def test_result_is_hidden_from_student_for_release_hours(self):
        with bypass_rls():
            self._final("40", self.center)
            self.assertIsNone(self._student_exam_score())
            staff_view = transcript.build_student_transcript(student=self.enrollments[0].student, organization=self.org)
            staff_rows = [row for sem in staff_view["semesters"] for row in sem["rows"]]
            self.assertEqual(staff_rows[0]["result"]["exam_score"], Decimal("40"))
            later = timezone.now() + timedelta(hours=25)
            with mock.patch("django.utils.timezone.now", return_value=later):
                self.assertEqual(self._student_exam_score(), Decimal("40"))
            with mock.patch("core.runtime_settings_exam_scores.release_hours", return_value=0):
                self.assertEqual(self._student_exam_score(), Decimal("40"))

    def test_midterm_hidden_in_student_journal_view_until_release(self):
        enrollment = self.enrollments[0]
        with bypass_rls():
            service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(enrollment.pk), "score": "21"}],
                by_user=self.center,
                sheet=self._midterm_sheet(),
            )
            component = interim_components.ensure_kollokviums(self.offering)[0]
            rows = [{"component": component, "score": Decimal("21"), "auto": True}]
            hidden, entry_kwargs = release.student_interim_view(enrollment, rows)
            self.assertIsNone(hidden[0]["score"])
            self.assertIsNotNone(hidden[0]["release_at"])
            self.assertFalse(any(s.component_id == component.pk for s in entry_kwargs["component_scores"]))
            later = timezone.now() + timedelta(hours=25)
            with mock.patch("django.utils.timezone.now", return_value=later):
                shown, kwargs = release.student_interim_view(enrollment, rows)
            self.assertEqual(shown[0]["score"], Decimal("21"))
            self.assertEqual(kwargs, {})
