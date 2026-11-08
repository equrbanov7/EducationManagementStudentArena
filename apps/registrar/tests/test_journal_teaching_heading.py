"""Current teaching share headings never misattribute anonymous historical lessons."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from apps.registrar.journal_assignment_sources import teacher_journal_plan_hours
from apps.registrar.journal_extras import journal_teaching_summary
from apps.registrar.journal_shares import FULL, Scope, journal_scope
from apps.registrar.models import CourseOffering, JournalShare, Lesson
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class JournalTeachingHeadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("heading-scope")
        cls.stack = make_structure(cls.org, code="HEADING")
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
        cls.lecture = get_user_model().objects.create_user("heading-lecture", first_name="Lecture", last_name="Teacher")
        cls.seminar = get_user_model().objects.create_user("heading-seminar", first_name="Seminar", last_name="Teacher")
        for teacher, kind in ((cls.lecture, "lecture"), (cls.seminar, "seminar")):
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS)
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=teacher, activity=kind, hours=30
            )
        cls.course = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.stack["group"],
            period=cls.stack["period"],
            instructor=cls.lecture,
            lesson_hours=60,
        )
        JournalShare.objects.create(organization=cls.org, offering=cls.course, teacher=cls.lecture, kinds=["lecture"])
        JournalShare.objects.create(organization=cls.org, offering=cls.course, teacher=cls.seminar, kinds=["seminar"])
        for kind, instructor, hours in (("lecture", cls.lecture, 4), ("seminar", cls.seminar, 6), ("lecture", None, 2)):
            Lesson.objects.create(
                organization=cls.org,
                offering=cls.course,
                kind=kind,
                instructor=instructor,
                hours=hours,
                date=timezone.localdate(),
            )

    def own(self, teacher):
        return journal_teaching_summary(self.course, personal_actor=teacher, scope=journal_scope(teacher, self.course))

    def test_lecture_only_heading_uses_own30_plan_and_restricted_history(self):
        summary = self.own(self.lecture)
        self.assertEqual(30, summary["total"])
        self.assertEqual(6, summary["held_total"])
        self.assertEqual(["lecture"], [row["kind"] for row in summary["kinds"]])
        self.assertEqual(30, summary["kinds"][0]["planned"])
        self.assertEqual(["lecture"], [row["kind"] for row in summary["history"]["kinds"]])
        html = render_to_string(
            "registrar/partials/_journal_teaching_heading.html", {"teaching_summary": summary, "offering": self.course}
        )
        # Sahib 2026-11-09: seminarın KİMƏ təyin olunduğu görünür (oxu çipi), amma cəmlər öz payıdır.
        self.assertEqual(
            summary["others"],
            [{"kind": "seminar", "label": "Seminar", "planned": 30, "held": 6, "teachers": ["Seminar Teacher"]}],
        )
        self.assertIn("Seminar Teacher", html)
        self.assertIn("jd2-teach-kind--other", html)
        self.assertNotIn("/ 60", html)
        self.assertIn("/ 30", html)

    def test_seminar_teacher_sees_only_seminar30_and_own_actual_author(self):
        summary = self.own(self.seminar)
        self.assertEqual((30, 6), (summary["total"], summary["held_total"]))
        self.assertEqual(["Seminar Teacher"], summary["kinds"][0]["teachers"])
        self.assertEqual("seminar", summary["kinds"][0]["kind"])
        self.assertEqual(
            [("lecture", 30, 6, ["Lecture Teacher"])],
            [(o["kind"], o["planned"], o["held"], o["teachers"]) for o in summary["others"]],
        )

    def test_admin_full_history_with_unknown_author_not_owner_fallback(self):
        summary = journal_teaching_summary(self.course)
        self.assertFalse(summary["personal"])
        self.assertNotIn("others", summary)
        self.assertEqual((60, 12), (summary["total"], summary["held_total"]))
        lecture = next(row for row in summary["kinds"] if row["kind"] == "lecture")
        self.assertEqual(2, len(lecture["teachers"]))
        self.assertIn("Lecture Teacher", lecture["teachers"])
        self.assertIn("Müəllifi göstərilməyən tarixçə", lecture["teachers"])
        self.assertEqual(3, Lesson.objects.filter(offering=self.course).count())

    def test_anonymous_own_entered_lesson_remains_unknown_teaching_author(self):
        Lesson.objects.filter(offering=self.course, instructor=None).update(created_by=self.lecture)
        summary = self.own(self.lecture)
        self.assertIn("Müəllifi göstərilməyən tarixçə", summary["kinds"][0]["teachers"])
        self.assertEqual(4, Lesson.objects.filter(offering=self.course, instructor=self.lecture).first().hours)

    def test_draft_assignment_never_supplies_personal_official_plan(self):
        type(self.task).objects.filter(pk=self.task.pk).update(status="draft")
        plans = teacher_journal_plan_hours(organization=self.org, teacher_id=self.lecture.pk)
        self.assertEqual({}, plans)
        summary = self.own(self.lecture)
        self.assertEqual(0, summary["total"])
        self.assertEqual(6, summary["held_total"])

    def test_scope_is_honored_even_if_current_assignment_has_other_kind(self):
        narrow = Scope(full=False, kinds=frozenset({"seminar"}), teacher_id=self.lecture.pk)
        summary = journal_teaching_summary(self.course, personal_actor=self.lecture, scope=narrow)
        # Existing own lecture columns remain readable under the established scope override.
        self.assertEqual(4, summary["held_total"])
        self.assertNotIn("Müəllifi göstərilməyən tarixçə", summary["kinds"][0]["teachers"])

    def test_foreign_teacher_with_no_plan_never_receives_full_course60_as_own_plan(self):
        other = get_user_model().objects.create_user("heading-other")
        summary = journal_teaching_summary(
            self.course, personal_actor=other, scope=Scope(full=False, kinds=frozenset(), teacher_id=other.pk)
        )
        self.assertEqual((0, 0), (summary["total"], summary["held_total"]))
        self.assertEqual([], summary["kinds"])

    def test_explicit_language_cohort_plan_stays_independent_of_imported_workload(self):
        with (
            patch(
                "apps.registrar.language_cohort_journal.teacher_assignments",
                return_value={(None, None, self.course.pk): {"seminar"}},
            ),
            patch("apps.registrar.language_cohort_journal.hours_for_offering", return_value={"seminar": 75}),
        ):
            summary = journal_teaching_summary(self.course, personal_actor=self.seminar, scope=FULL)
        self.assertEqual((75, 6), (summary["total"], summary["held_total"]))
        self.assertEqual(["seminar"], [kind["kind"] for kind in summary["kinds"]])
