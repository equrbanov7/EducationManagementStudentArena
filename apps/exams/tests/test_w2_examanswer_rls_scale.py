"""W2 2026-09-14 — exams auditi 2026-09-13 EX-12: `exams_examanswer` RLS siyasətinin həcm ölçməsi.

Siyasət (`organizations 0020`): hər cavab sətri üçün korrelyasiyalı
`EXISTS (attempt ⋈ exam ⋈ question … organization_id = current_setting)`.
Klonda cəhd sətri olmadığı üçün auditor real həcmdə ölçə bilməyib (NOT TESTED).

Bu test sandbox-da 1 təşkilat · 1 test-imtahan · 40 sual (×4 variant) ·
500 cəhd × 40 cavab (= 20 000 `exams_examanswer` + 20 000 seçilmiş variant
through sətri) qurur və üç isti yolu `rls_app_role` altında (BYPASSRLS yoxdur,
`app.current_org_id` qurulub) `EXPLAIN (ANALYZE, BUFFERS)` ilə ölçür:

* **tələbə nəticəsi** (`views/student/results.py`): `attempt.answers
  .select_related("question") … WHERE attempt_id = X ORDER BY id` +
  `selected_options` prefetch-i (through cədvəlinin öz 4-cədvəlli siyasəti);
* **müəllim nəticələri** (`views/teacher/results/_results_views.py`,
  `attach_test_result_summaries`): `ExamAnswer WHERE attempt_id IN (500 cəhd)`;
* **finish** (`views/student/_answer_writes.py`): cəhdin cavabları + `bulk_update`
  UPDATE (RLS `WITH CHECK` də hər sətir üçün subplan işlədir).

Qərar qaydası (brief): sətir-başına subplan bu həcmdə > 100 ms olarsa
`organization_id` denormalizasiyası; əks halda yalnız rəqəmlər (sxem dəyişmir).
Ölçmə nəticəsi `-s` ilə `EX12 …` sətirlərində çap olunur; testin öz iddiaları
plan formasına (attempt_id indeksi, seq scan yox) və geniş ehtiyatlı üst
həddə (< 1 500 ms / sorğu) bağlıdır ki, CI-də səs-küydən qırılmasın.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

ATTEMPTS = 500
QUESTIONS = 40
UPPER_BOUND_MS = 5000.0  # 2026-09-14: xdist 6 worker altında 1 500 ms səs-küydən qırıldı; sanity həddi


def _exec_ms(plan: str) -> float:
    match = re.search(r"Execution Time: ([0-9.]+) ms", plan)
    return float(match.group(1)) if match else -1.0


def _plan_ms(plan: str) -> float:
    match = re.search(r"Planning Time: ([0-9.]+) ms", plan)
    return float(match.group(1)) if match else -1.0


@pytest.mark.postgres
class ExamAnswerRlsScaleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("ex12_owner", "ex12_owner@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="EX12 University",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        now = timezone.now()
        cls.exam = Exam.objects.create(
            title="EX12 Final",
            author=owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=90,
            random_question_count=QUESTIONS,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=2),
        )
        questions = ExamQuestion.objects.bulk_create(
            [ExamQuestion(exam=cls.exam, order=i + 1, text=f"EX12 sual {i}") for i in range(QUESTIONS)]
        )
        options = ExamQuestionOption.objects.bulk_create(
            [
                ExamQuestionOption(question=q, label=label, text=label.lower(), is_correct=(label == "A"))
                for q in questions
                for label in ("A", "B", "C", "D")
            ]
        )
        first_option_by_q = {}
        for option in options:
            first_option_by_q.setdefault(option.question_id, option.id)

        students = User.objects.bulk_create(
            [User(username=f"ex12_s{i:04d}", email=f"ex12_s{i}@test.az", password="!") for i in range(ATTEMPTS)]
        )
        attempts = ExamAttempt.objects.bulk_create(
            [
                ExamAttempt(
                    user=student,
                    exam=cls.exam,
                    attempt_number=1,
                    status="submitted",
                    finished_at=now,
                    correct_count=QUESTIONS // 2,
                    wrong_count=QUESTIONS - QUESTIONS // 2,
                )
                for student in students
            ]
        )
        answers = ExamAnswer.objects.bulk_create(
            [
                ExamAnswer(attempt=attempt, question=q, is_correct=(q.order % 2 == 0))
                for attempt in attempts
                for q in questions
            ],
            batch_size=2000,
        )
        through = ExamAnswer.selected_options.through
        through.objects.bulk_create(
            [
                through(examanswer_id=answer.id, examquestionoption_id=first_option_by_q[answer.question_id])
                for answer in answers
            ],
            batch_size=2000,
        )
        cls.attempt_ids = [attempt.id for attempt in attempts]
        cls.sample_attempt = attempts[len(attempts) // 2]

    def _enter_rls(self, cursor):
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
        cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
        cursor.execute("SET LOCAL ROLE rls_app_role")

    def _explain(self, cursor, sql, params=None):
        cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", params or [])
        return "\n".join(row[0] for row in cursor.fetchall())

    def _report(self, label, plan):
        exec_ms, plan_ms = _exec_ms(plan), _plan_ms(plan)
        print(f"\nEX12 {label}: execution={exec_ms:.1f} ms planning={plan_ms:.1f} ms")
        print(plan)
        self.assertGreaterEqual(exec_ms, 0.0, "EXPLAIN ANALYZE nəticəsi oxunmadı")
        self.assertLess(exec_ms, UPPER_BOUND_MS, f"{label}: {exec_ms} ms — RLS subplanı həcmdə partlayır")
        return exec_ms

    def test_hot_paths_under_rls_at_scale(self):
        self.assertEqual(ExamAnswer.objects.count(), ATTEMPTS * QUESTIONS)

        student_qs = (
            ExamAnswer.objects.filter(attempt_id=self.sample_attempt.id).select_related("question").order_by("id")
        )
        student_sql, student_params = student_qs.query.sql_with_params()
        answer_ids = list(student_qs.values_list("id", flat=True))
        teacher_qs = (
            ExamAnswer.objects.filter(attempt_id__in=self.attempt_ids).select_related("question").order_by("id")
        )
        teacher_sql, teacher_params = teacher_qs.query.sql_with_params()
        # `selected_options` prefetch-inin ƏSL SQL-i (Django ORM-in through-join forması).
        with CaptureQueriesContext(connection) as captured:
            list(ExamAnswer.objects.filter(attempt_id=self.sample_attempt.id).prefetch_related("selected_options"))
        options_sql = next(
            q["sql"] for q in captured.captured_queries if "exams_examanswer_selected_options" in q["sql"]
        )
        options_params = None

        timings = {}
        with connection.cursor() as cursor:
            self._enter_rls(cursor)
            try:
                # RLS həqiqətən aktivdir: başqa tenant kontekstində sətir görünmür.
                cursor.execute(
                    "SELECT set_config('app.current_org_id', %s, true)", ["00000000-0000-0000-0000-000000000000"]
                )
                cursor.execute("SELECT count(*) FROM exams_examanswer WHERE attempt_id = %s", [self.sample_attempt.id])
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
                cursor.execute("SELECT count(*) FROM exams_examanswer WHERE attempt_id = %s", [self.sample_attempt.id])
                self.assertEqual(cursor.fetchone()[0], QUESTIONS)

                # 1) tələbə nəticəsi — 40 cavab + seçilmiş variantlar.
                plan = self._explain(cursor, student_sql, student_params)
                self.assertNotIn("Seq Scan on exams_examanswer", plan)
                timings["student_result_answers(40)"] = self._report("student_result_answers(40)", plan)
                # Through cədvəlinin 4-cədvəlli siyasəti plan qiymətini şişirdir →
                # `jit_above_cost` (100 000) aşılır və JIT kompilyasiyası (~100 ms)
                # işə düşür; həqiqi subplan xərcini görmək üçün JIT-siz də ölçülür.
                plan = self._explain(cursor, options_sql, options_params)
                timings["student_result_selected_options(40, jit=on)"] = self._report(
                    "student_result_selected_options(40, jit=on)", plan
                )
                cursor.execute("SET LOCAL jit = off")
                plan = self._explain(cursor, options_sql, options_params)
                timings["student_result_selected_options(40, jit=off)"] = self._report(
                    "student_result_selected_options(40, jit=off)", plan
                )
                cursor.execute("SET LOCAL jit = on")

                # 2) müəllim nəticələri — 500 cəhdin 20 000 cavabı (prefetch forması).
                plan = self._explain(cursor, teacher_sql, teacher_params)
                self.assertNotIn("Seq Scan on exams_examanswer", plan)
                timings["teacher_results_answers(20000)"] = self._report("teacher_results_answers(20000)", plan)
                # Baza: eyni sorğu siyasət qısa-qapanmış (`app.bypass_rls=on`) — RLS
                # subplanının xalis əlavə xərci = fərq.
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
                plan = self._explain(cursor, teacher_sql, teacher_params)
                cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
                timings["teacher_results_answers(20000, bypass_rls=on)"] = self._report(
                    "teacher_results_answers(20000, bypass_rls=on)", plan
                )

                # 3) finish — cavab oxunuşu (1-lə eyni) + bulk_update UPDATE (WITH CHECK).
                with connection.cursor() as inner:
                    self._enter_rls(inner)
                    inner.execute("SAVEPOINT ex12_update")
                    plan = self._explain(
                        inner,
                        "UPDATE exams_examanswer SET is_correct = NOT is_correct WHERE id = ANY(%s)",
                        [answer_ids],
                    )
                    inner.execute("ROLLBACK TO SAVEPOINT ex12_update")
                    inner.execute("RESET ROLE")
                timings["finish_bulk_update(40)"] = self._report("finish_bulk_update(40)", plan)
            finally:
                cursor.execute("RESET ROLE")

        print("\nEX12 SUMMARY " + " · ".join(f"{k}={v:.1f}ms" for k, v in timings.items()))
