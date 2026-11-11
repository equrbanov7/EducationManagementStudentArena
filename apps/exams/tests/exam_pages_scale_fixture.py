"""Müəllim imtahan səhifələrinin sürət testləri üçün miqyaslı fikstur (sahib 2026-11-11: «burada da ləngdir»).

Real ölçüyə yaxın imtahan toplu (``bulk_create``) yaradılır: N sual × 5 variant, G reyestr qrupu × S tələbə,
hər tələbəyə bir bitmiş cəhd × A cavab (seçilmiş variantı ilə). Büdcə testləri kiçik və böyük fiksturu
müqayisə edir — sorğu sayı sətir sayından asılı olmamalıdır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.tests.test_exam_assignees_2026_10_27 import _Fixture
from apps.exams.tests.test_w4_wizard_units import _login
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class ExamPagesScaleFixture(_Fixture):
    """``_build(questions, groups, students_each, answers_each)`` → imtahan + suallar + cəhdlər."""

    _serial = 0

    def _questions(self, exam, count, *, options=5, start=1, language="az", is_active=True):
        with bypass_rls():
            questions = ExamQuestion.objects.bulk_create(
                [
                    ExamQuestion(
                        exam=exam,
                        text=f"Sual mətni nömrə {index}",
                        order=index,
                        answer_mode="single",
                        language=language,
                        is_active=is_active,
                    )
                    for index in range(start, start + count)
                ]
            )
            ExamQuestionOption.objects.bulk_create(
                [
                    ExamQuestionOption(
                        question=question, label="ABCDE"[slot], text=f"{question.order}-{slot}", is_correct=slot == 0
                    )
                    for question in questions
                    for slot in range(options)
                ]
            )
        return questions

    def _students(self, groups, students_each):
        type(self)._serial += 1
        tag = f"x{type(self)._serial}"
        role = self.org.roles.get(name="student")
        with bypass_rls():
            units = OrgUnit.objects.bulk_create(
                [
                    OrgUnit(
                        organization=self.org,
                        parent=self.faculty,
                        name=f"{800 + index} {tag} az",
                        slug=f"xp-{tag}-{index}",
                        unit_type=OrgUnitType.GROUP,
                    )
                    for index in range(groups)
                ]
            )
            users = User.objects.bulk_create(
                [
                    User(username=f"{tag}_{g}_{s}", email=f"{tag}_{g}_{s}@test.az", first_name="Ad", last_name=f"S{s}")
                    for g in range(groups)
                    for s in range(students_each)
                ]
            )
            Membership.objects.bulk_create(
                [Membership(user=user, organization=self.org, role=role, is_active=True) for user in users]
            )
            StudentAcademicRecord.objects.bulk_create(
                [
                    StudentAcademicRecord(
                        organization=self.org,
                        student=user,
                        program=self.program,
                        curriculum=self.curriculum,
                        group=units[index // students_each],
                        admission_year=2024,
                    )
                    for index, user in enumerate(users)
                ]
            )
        return units, users

    def _attempts(self, exam, users, questions, answers_each):
        """Hər tələbəyə bir bitmiş cəhd; ilk ``answers_each`` suala cavab (cüt nömrəli tələbə düz cavablayır)."""
        delivered = questions[:answers_each]
        with bypass_rls():
            first_option = {}
            for option in ExamQuestionOption.objects.filter(question__in=delivered).order_by("question_id", "label"):
                first_option.setdefault(option.question_id, []).append(option)
            attempts = ExamAttempt.objects.bulk_create(
                [
                    ExamAttempt(
                        exam=exam,
                        user=user,
                        status="submitted",
                        finished_at=timezone.now(),
                        correct_count=answers_each if index % 2 == 0 else 0,
                        wrong_count=0 if index % 2 == 0 else answers_each,
                    )
                    for index, user in enumerate(users)
                ]
            )
            answers = ExamAnswer.objects.bulk_create(
                [
                    ExamAnswer(attempt=attempt, question=question, is_correct=index % 2 == 0)
                    for index, attempt in enumerate(attempts)
                    for question in delivered
                ]
            )
            through = ExamAnswer.selected_options.through
            per_attempt = len(delivered)
            through.objects.bulk_create(
                [
                    through(
                        examanswer_id=answer.pk,
                        examquestionoption_id=first_option[answer.question_id][
                            0 if (position // per_attempt) % 2 == 0 else 1
                        ].pk,
                    )
                    for position, answer in enumerate(answers)
                ]
            )
        return attempts

    def _build(self, *, questions, groups=0, students_each=0, answers_each=0, title="Scale", **exam_kwargs):
        exam = self._exam(title=title, **exam_kwargs)
        question_rows = self._questions(exam, questions)
        units, users, attempts = [], [], []
        if groups:
            units, users = self._students(groups, students_each)
            exam.allowed_units.add(*units)
            if answers_each:
                attempts = self._attempts(exam, users, question_rows, answers_each)
        return exam, question_rows, users, attempts

    def _client(self, user=None):
        return _login(user or self.teacher, self.org)

    @staticmethod
    def _measure(call):
        with CaptureQueriesContext(connection) as ctx:
            response = call()
        return ctx, response
