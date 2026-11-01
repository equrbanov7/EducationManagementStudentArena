"""Written question ceilings and evaluated workbook grouping regressions."""

from io import BytesIO
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from openpyxl import load_workbook

from apps.exams.forms import ExamQuestionCreateForm
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamGradeEvent, ExamQuestion, QuestionBlock
from apps.exams.services.manual_grading import answer_max_points, apply_single_answer_grade
from apps.exams.services.results_export import HEADERS, build_results_xlsx
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls


class WrittenMaximumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        teacher = get_user_model().objects.create_user("written-max", password="pw")
        org = Organization.objects.create(
            name="Written maximum", owner=teacher, org_type=OrganizationType.SCHOOL, status="active"
        )
        cls.exam = Exam.objects.create(title="Written", author=teacher, organization=org, exam_type="written")
        cls.block = QuestionBlock.objects.create(exam=cls.exam, name="Block")

    def form(self, points, *, instance=None, omit=False):
        data = {"text": "Sual", "language": "az", "block": self.block.pk}
        if not omit:
            data["points"] = points
        return ExamQuestionCreateForm(
            data,
            instance=instance,
            exam_type="written",
            exam=self.exam,
            subject_blocks=self.exam.question_blocks.all(),
        )

    def test_create_and_edit_persist_per_question_maximum(self):
        form = self.form("12")
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save(commit=False)
        question.exam = self.exam
        question.save()
        self.assertEqual(question.points, 12)
        edit = self.form("25", instance=question)
        self.assertTrue(edit.is_valid(), edit.errors)
        edit.save()
        question.refresh_from_db()
        self.assertEqual(question.points, 25)
        # Grading keeps the ceiling delivered to this student, even after editing.
        answer = SimpleNamespace(question=question, question_snapshot={"points": 12})
        self.assertEqual(answer_max_points(answer), 12)

    def test_invalid_maximum_is_rejected_and_old_client_preserves_existing(self):
        for value in ("0", "-1", "2.5", "oops"):
            form = self.form(value)
            self.assertFalse(form.is_valid())
            self.assertIn("points", form.errors)
        question = ExamQuestion.objects.create(exam=self.exam, block=self.block, text="Sual", points=17)
        form = self.form(None, instance=question, omit=True)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().points, 17)

    def test_grading_uses_delivered_maximum_after_question_edit(self):
        student = get_user_model().objects.create_user("written-max-student", password="pw")
        question = ExamQuestion.objects.create(exam=self.exam, block=self.block, text="Sual", points=12)
        attempt = ExamAttempt.objects.create(exam=self.exam, user=student, status="submitted")
        answer = ExamAnswer.objects.create(
            attempt=attempt, question=question, text_answer="Cavab", question_snapshot={"points": 12}
        )
        form = self.form("25", instance=question)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        with bypass_rls():
            apply_single_answer_grade(answer_id=answer.pk, score=25, grader=self.exam.author)
        answer.refresh_from_db()
        self.assertEqual(answer.teacher_score, 12)
        self.assertEqual(answer.question_snapshot["points"], 12)
        event = ExamGradeEvent.objects.get(attempt=attempt)
        self.assertEqual((event.max_points, event.new_score), (12, 12))


class GroupWorkbookTests(SimpleTestCase):
    def workbook(self, rows, *, grouped=True):
        return load_workbook(
            BytesIO(build_results_xlsx(rows, sheet_title="Results", filename_stem="results", group_sheets=grouped)[2])
        )

    def test_tabs_and_subject_order_keep_every_row_once(self):
        rows = [
            {"groups": "Q10", "subject": "Riyaziyyat", "student": "Son"},
            {"groups": "Q2", "subject": "İngilis dili", "student": "=malicious"},
            {"groups": "Q2", "subject": "Ədəbiyyat", "student": "İlk"},
            {"groups": "Q2", "subject": "Coğrafiya", "student": "Ara"},
        ]
        workbook = self.workbook(rows)
        self.assertEqual(workbook.sheetnames, ["Q2", "Q10"])
        self.assertEqual(sum(sheet.max_row - 1 for sheet in workbook), len(rows))
        sheet = workbook["Q2"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), HEADERS)
        self.assertEqual([sheet.cell(row, 9).value for row in (2, 3, 4)], ["Coğrafiya", "Ədəbiyyat", "İngilis dili"])
        self.assertEqual(sheet["D4"].data_type, "s")
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, "A1:AD4")
        self.assertEqual([sheet.cell(row, 1).value for row in (2, 3, 4)], [1, 2, 3])

    def test_invalid_long_and_colliding_group_labels_remain_separate(self):
        groups = ["A/B", "A:B", "a b", "x" * 45 + "1", "x" * 45 + "2", "", "Qrupsuz"]
        workbook = self.workbook({"groups": group, "student": str(index)} for index, group in enumerate(groups))
        self.assertEqual(len(workbook.sheetnames), len(groups))
        self.assertEqual(len({name.casefold() for name in workbook.sheetnames}), len(groups))
        self.assertTrue(all(len(name) <= 31 for name in workbook.sheetnames))
        self.assertEqual(sum(sheet.max_row - 1 for sheet in workbook), len(groups))

    def test_empty_export_has_header_and_single_exam_keeps_caller_order(self):
        self.assertEqual(self.workbook([]).active.max_row, 1)
        workbook = self.workbook([{"student": "Z"}, {"student": "A"}], grouped=False)
        self.assertEqual(workbook.sheetnames, ["Results"])
        self.assertEqual([workbook.active.cell(row, 4).value for row in (2, 3)], ["Z", "A"])
