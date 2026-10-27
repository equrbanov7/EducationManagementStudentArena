"""İmtahan sehrbazının «Saxla»sı — çox qrupda sorğu büdcəsi (sahib 2026-10-27).

Sahib: «bu hissə birdən çox qrup yükləyəndə gec olur» — 10 reyestr qrupu seçilmiş midtermin saxlanması
«Saxlanılır…»da ilişirdi. Ölçü (10 qrup × 30 tələbə, ``config.settings.test``; PIN hash-i onsuz da Celery-dədir):

==========================================================  ===========  ==========
ssenari                                                     əvvəl        sonra
==========================================================  ===========  ==========
yaratma (10 qrup, 300 tələbə)                               85 / 0.28 s  dəyişməyib
nəticəli midterm: 5 qrupa +5 qrup (150 bitmiş cəhd)         4772 / 3.8 s 98 / 0.4 s
==========================================================  ===========  ==========

Kök səbəb: qrup əlavəsi bağlı jurnalları dəyişir → ``exam_journal_link.after_exam_saved`` BÜTÜN rəsmi midterm
cəhdlərini yenidən yazırdı (cəhd başına ~30 sorğu: kilid, bal, audit, bildiriş) — ``on_commit``-də, amma
``ATOMIC_REQUESTS`` altında on_commit request-in içindədir. İndi Celery task-ıdır (``exams.resync_exam_journal``);
növbə əlçatmazdırsa əvvəlki kimi yerində işləyir. Yazılan ballar / audit sətirləri eynidir (testlərdə task eager-dir).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup, _login
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls

#: Yaratma POST-u (middleware daxil) — qrup / tələbə sayından ASILI DEYİL.
CREATE_BUDGET = 88
#: Nəticəli midtermə qrup əlavəsi — cəhd sayından asılı deyil (yenidən sinxron Celery-dədir).
EDIT_WITH_RESULTS_BUDGET = 102

_HASH_DELAY = "apps.exams.tasks.hash_pending_student_pins.delay"
_RESYNC_DELAY = "apps.exams.tasks.resync_exam_journal.delay"


class _ManyGroupsSetup(_LinkSetup):
    def _build_groups(self, n_groups, n_students, *, prefix):
        User = get_user_model()
        role = self.org.roles.get(name="student")
        units = []
        with bypass_rls():
            for g in range(n_groups):
                unit = OrgUnit.objects.create(
                    organization=self.org,
                    name=f"{prefix.upper()}{g}",
                    slug=f"{prefix}-g{g}",
                    unit_type=OrgUnitType.GROUP,
                )
                offering = CourseOffering.objects.create(
                    organization=self.org,
                    subject=self.subject,
                    period=self.period,
                    group=unit,
                    instructor=self.teacher,
                    lesson_hours=30,
                )
                for s in range(n_students):
                    student = User.objects.create_user(f"{prefix}_{g}_{s}", f"{prefix}_{g}_{s}@qku.edu.az", "pw")
                    Membership.objects.create(user=student, organization=self.org, role=role, is_active=True)
                    StudentAcademicRecord.objects.create(
                        organization=self.org,
                        student=student,
                        program=self.program,
                        curriculum=self.curriculum,
                        group=unit,
                        admission_year=2024,
                    )
                    Enrollment.objects.create(organization=self.org, student=student, offering=offering)
                units.append(unit)
        return units

    def _post(self, url, units, **extra):
        client = _login(self.center, self.org)
        payload = self._payload(allowed_units=[str(u.pk) for u in units], **extra)
        with CaptureQueriesContext(connection) as ctx:
            with self.captureOnCommitCallbacks(execute=True):
                response = client.post(url + "?modal=1", payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["success"], response.content[:500])
        return ctx

    def _create(self, units, title="JS Loop"):
        self._post(reverse("exams:create_exam"), units, title=title)
        with bypass_rls():
            return Exam.objects.get(title=title)

    def _edit(self, exam, units):
        return self._post(reverse("exams:edit_exam", kwargs={"slug": exam.slug}), units, title=exam.title)

    def _with_results(self, exam, units):
        """İmtahanı aktiv test midterminə çevir + ``units`` qruplarının hər tələbəsinə bitmiş cəhd."""
        with bypass_rls():
            for order in range(1, 4):
                question = ExamQuestion.objects.create(exam=exam, order=order, text=f"Q{order}", points=1)
                ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
                ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
            Exam.objects.filter(pk=exam.pk).update(is_active=True)
            student_ids = list(
                StudentAcademicRecord.objects.filter(group__in=units).values_list("student_id", flat=True)
            )
            started = timezone.now() - datetime.timedelta(hours=1)
            ExamAttempt.objects.bulk_create(
                [
                    ExamAttempt(
                        user_id=student_id,
                        exam=exam,
                        status="submitted",
                        started_at=started,
                        finished_at=timezone.now(),
                    )
                    for student_id in student_ids
                ]
            )
        return student_ids

    def _scores(self, exam):
        with bypass_rls():
            return ComponentScore.objects.filter(exam_source__exam_id=exam.pk).count()


class ExamSaveQueryBudgetTests(_ManyGroupsSetup):
    def test_create_cost_does_not_grow_with_groups_or_students(self):
        small_units = self._build_groups(1, 2, prefix="sm")
        large_units = self._build_groups(10, 30, prefix="lg")
        with mock.patch(_HASH_DELAY):
            small = self._post(reverse("exams:create_exam"), small_units, title="Small")
            large = self._post(reverse("exams:create_exam"), large_units, title="Large")
        self.assertLessEqual(len(large), len(small) + 2, [q["sql"][:120] for q in large.captured_queries])
        self.assertLessEqual(len(large), CREATE_BUDGET)

    def test_adding_groups_to_midterm_with_results_does_not_resync_in_request(self):
        def run(prefix, n_students):
            units = self._build_groups(4, n_students, prefix=prefix)
            with mock.patch(_HASH_DELAY), mock.patch(_RESYNC_DELAY) as resync:
                exam = self._create(units[:2], title=f"MT {prefix}")
                self._with_results(exam, units[:2])
                ctx = self._edit(exam, units)
            resync.assert_called_once_with(exam.pk, by_user_id=self.center.pk, change_log_id=None, relink=True)
            self.assertEqual(self._scores(exam), 0)  # bal köçürməsi request-də YOX
            sqls = [q["sql"] for q in ctx.captured_queries]
            self.assertFalse([s for s in sqls if 'INTO "registrar_componentscore"' in s])
            return len(ctx)

        small = run("ra", 1)
        large = run("rb", 30)
        self.assertLessEqual(large, small + 2)
        self.assertLessEqual(large, EDIT_WITH_RESULTS_BUDGET)


class ExamSaveResyncTaskTests(_ManyGroupsSetup):
    def _exam_with_results(self):
        units = self._build_groups(3, 2, prefix="rt")
        with mock.patch(_HASH_DELAY):
            exam = self._create(units[:1])
        students = self._with_results(exam, units[:1])
        return exam, units, students

    def test_task_writes_every_official_attempt_after_commit(self):
        exam, units, students = self._exam_with_results()
        with mock.patch(_HASH_DELAY):
            self._edit(exam, units)
        self.assertEqual(self._scores(exam), len(students))
        with bypass_rls():
            row = ComponentScore.objects.filter(exam_source__exam_id=exam.pk).first()
        self.assertEqual(row.score, Decimal("0"))

    def test_unavailable_queue_falls_back_to_inline_resync(self):
        exam, units, students = self._exam_with_results()
        with mock.patch(_HASH_DELAY), mock.patch(_RESYNC_DELAY, side_effect=OSError("broker down")) as resync:
            self._edit(exam, units)
        resync.assert_called_once()
        self.assertEqual(self._scores(exam), len(students))

    def test_unchanged_links_do_not_queue_a_resync(self):
        exam, units, _students = self._exam_with_results()
        with mock.patch(_HASH_DELAY), mock.patch(_RESYNC_DELAY) as resync:
            self._edit(exam, units[:1])
        resync.assert_not_called()
