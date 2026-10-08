"""Sual göndərişi — fənn/qrup siyahısı DƏRS YÜKÜNDƏN gəlir (müəllim rəyi S2, 2026-10-08).

Bug: «Yeni göndəriş» formasında fənn siyahısı boş idi («Sizə hələ fənn təyin
olunmayıb»), halbuki müəllimin «Dərs yüküm»ündə Payız 2026/27 üçün 3 fənn vardı.
Kök səbəb: siyahı YALNIZ köhnə imtahan kohortlarından (``exams.StudentGroup``) qurulurdu
— real bazada o cədvəl boşdur. İndi: cari semestrin açılışları (jurnal) + kafedranın
TƏSDİQLƏDİYİ bölgü + köhnə kohortlar; seçilə bilməyəndə səbəb göstərilir.
"""

import json
import re

from django.urls import reverse

from apps.exams.models import QuestionSubmission
from apps.exams.services.submission_sources import teacher_submission_sources
from apps.exams.tests.test_question_submission import VALID_TEXT, _Base
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrgUnitType

YEAR = "2026/2027"


class _LoadFixture(_Base):
    """Kafedra → ixtisas → iki qrup; cari Payız semestri; köhnə kohort YOXDUR."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.specialty = OrgUnit.objects.create(
            organization=cls.org, name="İnformatika ixtisası", unit_type=OrgUnitType.SPECIALTY, parent=cls.chair
        )
        cls.group_a = OrgUnit.objects.create(
            organization=cls.org, name="2233 İ", unit_type=OrgUnitType.GROUP, parent=cls.specialty
        )
        cls.group_b = OrgUnit.objects.create(
            organization=cls.org, name="2232 İ", unit_type=OrgUnitType.GROUP, parent=cls.specialty
        )
        cls.fall = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.spring = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Yaz",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2027-02-01",
            end_date="2027-06-30",
        )
        cls.subj_db = Subject.objects.create(organization=cls.org, code="QKU-1201", name="Verilənlər bazası")
        cls.networks = Subject.objects.create(organization=cls.org, code="QKU-1202", name="Kompüter şəbəkələri")
        cls.voip = Subject.objects.create(organization=cls.org, code="QKU-1203", name="VoIP sistemləri")

    def _task(self, status="distributed"):
        return TeachingTask.objects.create(organization=self.org, chair=self.chair, academic_year=YEAR, status=status)

    def _row(self, task, subject, groups, *, period=None, subject_text=""):
        row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            season="fall",
            period=period or self.fall,
            subject=subject,
            subject_text=subject_text,
            specialty=self.specialty,
            faculty=self.faculty,
            student_count=25,
            union_count=1,
            subgroup_count=1,
            lecture_plan=30,
            lecture_total=30,
            total_hours=30,
            credits_value=6,
        )
        row.groups.set(groups)
        TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.teacher, activity="lecture", hours=30
        )
        return row

    def _create_page(self):
        client = self._client_for(self.teacher)
        response = client.get(reverse("exams:question_submission_create"))
        self.assertEqual(response.status_code, 200)
        return client, response.content.decode()


class TeachingLoadSubjectsTests(_LoadFixture):
    def test_bug_repro_teaching_load_subjects_are_listed_without_legacy_cohorts(self):
        task = self._task()
        self._row(task, self.subj_db, [self.group_a, self.group_b])  # birləşmiş qrup
        self._row(task, self.networks, [self.group_a])
        CourseOffering.objects.create(
            organization=self.org, subject=self.voip, period=self.fall, group=self.group_b, instructor=self.teacher
        )
        _client, html = self._create_page()
        self.assertNotIn("Sizə hələ fənn təyin olunmayıb", html)
        # Fənn ADI əvvəl, kod ikinci dərəcəli.
        for label in (
            "Verilənlər bazası (QKU-1201)",
            "Kompüter şəbəkələri (QKU-1202)",
            "VoIP sistemləri (QKU-1203)",
        ):
            self.assertIn(label, html)
        # Reyestr qrupları çip kimi, qrup→fənn xəritəsi JSON-da.
        self.assertIn(f'value="u:{self.group_a.pk}"', html)
        self.assertIn(f'value="u:{self.group_b.pk}"', html)
        mapping = json.loads(
            re.search(r'<script id="qsubGroupsSubjects" type="application/json">(.*?)</script>', html, re.S).group(1)
        )
        self.assertEqual(
            {item["value"] for item in mapping[f"u:{self.group_b.pk}"]},
            {str(self.subj_db.pk), str(self.voip.pk)},
        )

    def test_unapproved_distribution_is_explained(self):
        self._row(self._task(status="approved"), self.subj_db, [self.group_a])
        _client, html = self._create_page()
        self.assertNotIn("Verilənlər bazası (QKU-1201)", html)
        self.assertIn("hələ təsdiqlənməyib", html)
        self.assertIn("data-qsub-subject-notice", html)

    def test_row_without_catalog_subject_is_explained(self):
        self._row(self._task(), None, [self.group_a], subject_text="Peşə təcrübəsi")
        sources = teacher_submission_sources(self.teacher, self.org)
        self.assertEqual(sources.subjects, [])
        self.assertTrue(any("Peşə təcrübəsi" in notice for notice in sources.notices))

    def test_load_only_in_other_semester_is_explained(self):
        self._row(self._task(), self.subj_db, [self.group_a], period=self.spring)
        sources = teacher_submission_sources(self.teacher, self.org, period=self.fall)
        self.assertEqual(sources.subjects, [])
        self.assertTrue(any("Cari semestrdə" in notice for notice in sources.notices))
        # Seçilmiş (yaz) semestr üçün isə görünür.
        spring = teacher_submission_sources(self.teacher, self.org, period=self.spring)
        self.assertEqual([s.pk for s in spring.subjects], [self.subj_db.pk])

    def test_no_load_at_all_says_subject_folder_is_not_needed(self):
        sources = teacher_submission_sources(self.teacher, self.org)
        self.assertEqual(sources.subjects, [])
        self.assertTrue(any("fənn qovluğu yaratmaq lazım deyil" in notice for notice in sources.notices))

    def test_other_teachers_load_is_not_listed(self):
        task = self._task()
        row = self._row(task, self.subj_db, [self.group_a])
        TeacherAssignment.objects.filter(row=row).update(teacher=self.chair_head)
        self.assertEqual(teacher_submission_sources(self.teacher, self.org).subjects, [])

    def test_submit_with_registry_group_routes_to_groups_chair(self):
        task = self._task()
        self._row(task, self.subj_db, [self.group_a, self.group_b])
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Verilənlər bazası — final",
                "language": "en",  # imtahan dili fənləri SÜZMÜR
                "subject": str(self.subj_db.pk),
                "exam_kind": "final",
                "group_ids": [f"u:{self.group_a.pk}", f"u:{self.group_b.pk}"],
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:300])
        submission = QuestionSubmission.objects.get(title="Verilənlər bazası — final")
        self.assertEqual(submission.subject_ref, self.subj_db)
        self.assertEqual(set(submission.group_label.split(", ")), {"2233 İ", "2232 İ"})
        self.assertIsNone(submission.student_group)
        # exams 0074: reyestr qrupları FK kimi də saxlanır (fakültə/kafedra süzgəci üçün).
        self.assertEqual(set(submission.registry_groups.all()), {self.group_a, self.group_b})
        self.assertEqual(submission.chair_unit, self.chair)
        self.assertEqual(submission.language, "en")

    def test_foreign_registry_group_is_rejected(self):
        task = self._task()
        self._row(task, self.subj_db, [self.group_a])
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Yad qrup",
                "language": "az",
                "subject": str(self.subj_db.pk),
                "exam_kind": "final",
                "group_ids": [f"u:{self.group_b.pk}"],  # müəllimin yükündə deyil
                "raw_text": VALID_TEXT,
            },
        )
        self.assertFalse(QuestionSubmission.objects.filter(title="Yad qrup").exists())

    def test_edit_prefills_registry_groups_from_label(self):
        task = self._task()
        self._row(task, self.subj_db, [self.group_a, self.group_b])
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Redaktə yoxlaması",
                "language": "az",
                "subject": str(self.subj_db.pk),
                "exam_kind": "final",
                "group_ids": [f"u:{self.group_a.pk}"],
                "raw_text": VALID_TEXT,
            },
        )
        submission = QuestionSubmission.objects.get(title="Redaktə yoxlaması")
        response = client.get(reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id}))
        html = response.content.decode()
        checked = re.search(rf'value="u:{self.group_a.pk}"[^>]*checked', html, re.S)
        self.assertIsNotNone(checked)
        self.assertIsNone(re.search(rf'value="u:{self.group_b.pk}"[^>]*\bchecked\b', html))


class LiveExamHintTests(_Base):
    """N1: «Sual göndərişləri»ndə canlı imtahan (Kahoot) sualları üçün yönləndirmə ipucu."""

    def _section(self, user):
        response = self._client_for(user).get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_teacher_sees_hint_with_link_to_my_exams(self):
        html = self._section(self.teacher)
        self.assertIn("data-qsub-live-hint", html)
        self.assertIn("Canlı imtahan (Kahoot) üçün suallar «İmtahanlarım» bölməsində əlavə olunur", html)
        self.assertIn("?section=my-exams", html)

    def test_reviewer_does_not_see_hint(self):
        self.assertNotIn("data-qsub-live-hint", self._section(self.exam_center))
