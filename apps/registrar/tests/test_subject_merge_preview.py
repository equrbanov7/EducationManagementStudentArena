"""«Fənləri birləşdir» — önizləmə: saylar, hər unikallıq qaydası üzrə toqquşma, iz, yoxlamalar (2026-10-19)."""

from __future__ import annotations

from django.urls import reverse

from apps.organizations.models import Organization
from apps.registrar import subject_merge
from apps.registrar.models import GroupElectiveChoice, Subject
from apps.registrar.models.curriculum_meta import PlanStatus
from core.constants import OrganizationType
from core.rls import bypass_rls

from .subject_merge_fixture import SubjectMergeBase


class PreviewTest(SubjectMergeBase):
    def _preview(self, target=None, sources=None):
        target = target or self.target
        sources = sources if sources is not None else [self.source]
        with bypass_rls():
            return subject_merge.preview(self.org, str(target.pk), [str(item.pk) for item in sources])

    def _codes(self, payload):
        return {item["code"] for item in payload["blocking"]}

    def test_counts_every_table_and_writes_nothing(self):
        self.build_full_source()
        payload = self._preview()
        counts = {table["key"]: table["count"] for table in payload["tables"]}
        self.assertEqual(
            counts,
            {
                "registrar.CourseOffering.subject": 1,
                "registrar.CurriculumSubject.subject": 1,
                "registrar.GroupElectiveChoice.chosen_subject": 1,
                "registrar.RetakeApplication.subject": 1,
                "registrar.ExamChanceGrant.subject": 1,
                "syllabus.Syllabus.subject": 2,
                "workload.TeachingTaskRow.subject": 1,
                "exams.StudentGroup.subjects": 2,
                "exams.Exam.subject": 1,
                "exams.QuestionBank.subject_ref": 1,
                "exams.QuestionSubmission.subject_ref": 1,
                "surveys.SurveyResponse.subject": 1,
                "subject_folder.SubjectFolder.subject": 1,
                "soft_json": 1,
            },
        )
        self.assertEqual(payload["total"], sum(counts.values()) - counts["registrar.ExamChanceGrant.subject"])
        self.assertTrue(payload["can_apply"], payload["blocking"])
        self.assertEqual(payload["archive_reason"], "Birləşdirildi → QA-SM-T")
        self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_offering_conflict_same_period_and_group(self):
        source_offering = self.offering(self.source, self.group1)
        self.offering(self.target, self.group1)
        payload = self._preview()
        self.assertFalse(payload["can_apply"])
        item = payload["blocking"][0]
        self.assertEqual(item["code"], "offering")
        self.assertEqual(
            item["message"], "2026/2027 Payız · 234 K: hər iki fənn üzrə açılış var — əvvəlcə birini ləğv edin."
        )
        urls = {link["url"] for link in item["links"]}
        self.assertIn(reverse("registrar:journal_detail", kwargs={"offering_id": source_offering.pk}), urls)

    def test_groupless_offerings_only_warn(self):
        self.offering(self.source, None)
        self.offering(self.target, None)
        payload = self._preview()
        self.assertTrue(payload["can_apply"])
        self.assertTrue(any("qrupsuz" in text for text in payload["warnings"]))

    def test_curriculum_conflict_in_locked_plans_blocks(self):
        for status in (PlanStatus.APPROVED, PlanStatus.CHAIR_REVIEW):
            with self.subTest(status=status):
                plan = self.plan(status, year=2020 + len(status), name=f"Plan {status}")
                self.plan_row(plan, self.source, semester=1)
                self.plan_row(plan, self.target, semester=1)
                payload = self._preview()
                self.assertIn("curriculum_row", self._codes(payload))
                self.assertIn("cu_plan=", payload["blocking"][0]["links"][0]["url"])

    def test_curriculum_conflict_in_draft_or_returned_plan_is_resolvable(self):
        for index, status in enumerate((PlanStatus.DRAFT, PlanStatus.RETURNED)):
            plan = self.plan(status, year=2030 + index)
            self.plan_row(plan, self.source, semester=2)
            self.plan_row(plan, self.target, semester=2)
        payload = self._preview()
        self.assertTrue(payload["can_apply"])
        self.assertEqual(payload["resolvable_total"], 2)

    def test_same_plan_different_semesters_warns(self):
        plan = self.plan()
        self.plan_row(plan, self.source, semester=1)
        self.plan_row(plan, self.target, semester=2)
        payload = self._preview()
        self.assertTrue(payload["can_apply"])
        self.assertTrue(any("müxtəlif semestrlərdədir" in text for text in payload["warnings"]))

    def test_enrollment_conflict_same_student_same_period(self):
        self.enroll(self.offering(self.source, self.group1), grade="40")
        self.enroll(self.offering(self.target, self.group2), grade="45")
        payload = self._preview()
        self.assertEqual(self._codes(payload), {"enrollment"})
        self.assertIn("Hər ikisində yekun qiymət yazılıb", payload["blocking"][0]["message"])

    def test_syllabus_period_and_base_conflicts(self):
        self.syllabus(self.source, period=self.period, author=self.teacher)
        self.syllabus(self.target, period=self.period, author=self.teacher)
        self.syllabus(self.source, author=self.teacher)
        self.syllabus(self.target, author=self.teacher)
        self.assertEqual(self._codes(self._preview()), {"syllabus_period", "syllabus_base"})

    def test_subject_folder_conflict(self):
        self.folder(self.source, period=self.period)
        self.folder(self.target, period=self.period)
        self.assertEqual(self._codes(self._preview()), {"subject_folder"})

    def test_active_retake_conflict(self):
        past = self.period.__class__.objects.create(
            organization=self.org,
            name="Yaz",
            period_type=self.period.period_type,
            academic_year="2025/2026",
            start_date="2026-02-10",
            end_date="2026-06-20",
        )
        source_enrollment = self.enroll(self.offering(self.source, self.group1, period=past))
        target_enrollment = self.enroll(self.offering(self.target, self.group1))
        self.retake(self.source, source_enrollment)
        self.retake(self.target, target_enrollment)
        self.assertEqual(self._codes(self._preview()), {"retake"})

    def test_closed_retake_does_not_conflict(self):
        enrollment = self.enroll(self.offering(self.source, self.group1))
        self.retake(self.source, enrollment, status="completed")
        self.retake(self.target, enrollment)
        self.assertTrue(self._preview()["can_apply"])

    def test_teaching_task_duplicate_row_conflict(self):
        task, _row = self.task_row(self.source, [self.group1])
        self.task_row(self.target, [self.group1], task=task)
        self.task_row(self.target, [self.group2], task=task)  # başqa qrup dəsti — toqquşmur
        payload = self._preview()
        self.assertEqual(self._codes(payload), {"task_row"})
        self.assertEqual(payload["blocking_total"], 1)

    def test_group_elective_choice_never_conflicts(self):
        with bypass_rls():
            for subject, block in ((self.source, "SB1"), (self.target, "SB2")):
                GroupElectiveChoice.objects.create(
                    organization=self.org,
                    group=self.group1,
                    period=self.period,
                    elective_group=block,
                    chosen_subject=subject,
                )
        self.assertTrue(self._preview()["can_apply"])

    def test_conflicts_between_two_sources_are_found_too(self):
        third = Subject.objects.create(organization=self.org, code="QA-SM-S2", name="VoIP sistemləri")
        self.offering(self.source, self.group1)
        self.offering(third, self.group1)
        self.assertEqual(self._codes(self._preview(sources=[self.source, third])), {"offering"})

    def test_digest_is_stable_and_tracks_rows(self):
        self.offering(self.source, self.group1)
        first = self._preview()["digest"]
        self.assertEqual(first, self._preview()["digest"])
        self.offering(self.source, self.group2)
        self.assertNotEqual(first, self._preview()["digest"])

    def test_credit_mismatch_with_graded_students_blocks(self):
        other = Subject.objects.create(organization=self.org, code="QA-SM-O", name="Vo IP sistemləri", ects=6)
        offering = self.offering(other, self.group1)
        self.enroll(offering, grade="40")
        self.enroll(offering, self.other_student)  # qiymətsiz — sayılmır
        payload = self._preview(sources=[other])
        self.assertFalse(payload["can_apply"])
        item = next(item for item in payload["blocking"] if item["code"] == "credit_mismatch")
        self.assertIn("1 tələbənin yekun qiyməti var", item["message"])
        self.assertIn("Əvvəlcə ECTS-i uyğunlaşdırın və ya hər iki kartı saxlayın", item["message"])
        self.assertFalse(any("Kredit fərqlidir" in text for text in payload["warnings"]))

    def test_credit_mismatch_with_completed_enrollment_blocks(self):
        from apps.registrar.models import Enrollment

        other = Subject.objects.create(organization=self.org, code="QA-SM-O", name="Vo IP sistemləri", ects=4)
        enrollment = self.enroll(self.offering(other, self.group1))
        with bypass_rls():
            Enrollment.objects.filter(pk=enrollment.pk).update(status=Enrollment.Status.COMPLETED)
        self.assertIn("credit_mismatch", self._codes(self._preview(sources=[other])))

    def test_credit_mismatch_without_grades_only_warns(self):
        other = Subject.objects.create(organization=self.org, code="QA-SM-O", name="Vo IP sistemləri", ects=6)
        self.enroll(self.offering(other, self.group1))
        payload = self._preview(sources=[other])
        self.assertTrue(payload["can_apply"], payload["blocking"])
        self.assertTrue(any("Kredit fərqlidir" in text for text in payload["warnings"]))

    def test_same_ects_with_grades_does_not_block(self):
        self.enroll(self.offering(self.source, self.group1), grade="40")
        self.assertTrue(self._preview()["can_apply"])

    def test_credit_and_name_warnings(self):
        other = Subject.objects.create(organization=self.org, code="QA-SM-O", name="Tamam başqa fənn", ects=7)
        warnings = self._preview(sources=[other])["warnings"]
        self.assertTrue(any("Kredit fərqlidir" in text and "QA-SM-O — 7 ECTS" in text for text in warnings))
        self.assertTrue(any("Adlar" in text for text in warnings))


class ValidationTest(SubjectMergeBase):
    def _error(self, target, sources):
        with bypass_rls(), self.assertRaises(subject_merge.MergeError) as caught:
            subject_merge.preview(self.org, target, sources)
        return caught.exception

    def test_rejections(self):
        foreign_org = Organization.objects.create(
            name="Başqa", slug="sm-other", org_type=OrganizationType.UNIVERSITY, owner=self.owner, status="active"
        )
        with bypass_rls():
            foreign = Subject.objects.create(organization=foreign_org, code="QA-SM-F", name="VoIP sistemləri")
        archived = Subject.objects.create(organization=self.org, code="QA-SM-A", name="A", is_archived=True)
        self.assertEqual(self._error(str(self.target.pk), [str(self.target.pk)]).code, "same_subject")
        self.assertEqual(self._error(str(self.target.pk), [str(foreign.pk)]).status, 404)
        self.assertEqual(self._error("not-a-uuid", [str(self.source.pk)]).status, 404)
        self.assertEqual(self._error(str(archived.pk), [str(self.source.pk)]).code, "target_archived")
        self.assertEqual(self._error(str(self.target.pk), []).code, "sources_required")
        self.assertEqual(self._error("", [str(self.source.pk)]).code, "target_required")
        many = [str(self.source.pk)] + [f"00000000-0000-0000-0000-0000000000{index:02d}" for index in range(10)]
        self.assertEqual(self._error(str(self.target.pk), many).code, "too_many_sources")

    def test_archived_source_is_allowed_with_warning(self):
        Subject.objects.filter(pk=self.source.pk).update(is_archived=True)
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
        self.assertTrue(any("artıq arxivdədir" in text for text in payload["warnings"]))
