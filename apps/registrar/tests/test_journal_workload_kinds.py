"""Planlaşdırılmış, hələ yazılmamış seminar/lab siyahıda və jurnal pilləsində görünür."""

from django.test import RequestFactory, TestCase

from apps.registrar import journal_window
from apps.registrar.journal_list_query import apply_kind_filter
from apps.registrar.models import CourseOffering, Lesson
from apps.registrar.page_contexts import attach_kind_labels
from apps.workload.constants import TaskStatus
from apps.workload.tests.factories import make_org, make_row, make_structure, make_task


class PlannedJournalKindsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("planned-journal-kinds")
        cls.stack = make_structure(cls.org, code="JPK")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=15, lab_total=15)
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.stack["group"],
            period=cls.stack["period"],
        )

    def test_all_three_planned_types_show_before_any_lesson_exists(self):
        self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())
        attach_kind_labels([self.offering])
        self.assertEqual(self.offering.slot_kinds, ["lecture", "seminar", "lab"])
        self.assertEqual(
            [tab["value"] for tab in journal_window.kind_tabs(self.offering, "seminar")],
            ["", "lecture", "seminar", "lab"],
        )
        request = RequestFactory().get("/jurnal/", {"kind": "seminar"})
        self.assertEqual(journal_window.resolve_request_kind(request, self.offering), "seminar")
        self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_planned_kind_filter_is_exact_to_group_period_and_tenant(self):
        other = make_structure(self.org, code="JPK2")
        wrong_group = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], group=other["group"], period=self.stack["period"]
        )
        wrong_period = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], group=self.stack["group"], period=other["period"]
        )
        other_org = make_org("planned-journal-other")
        foreign = make_structure(other_org, code="JPK3")
        foreign_offering = CourseOffering.objects.create(
            organization=other_org, subject=foreign["subject"], group=foreign["group"], period=foreign["period"]
        )
        found = set(apply_kind_filter(CourseOffering.objects.all(), "seminar").values_list("pk", flat=True))
        self.assertEqual(found, {self.offering.pk})
        for offering in (wrong_group, wrong_period, foreign_offering):
            attach_kind_labels([offering])
            self.assertEqual(offering.slot_kinds, [])

    def test_cancelled_load_does_not_supply_unrecorded_kinds(self):
        self.task.status = TaskStatus.CANCELLED
        self.task.save(update_fields=["status"])
        attach_kind_labels([self.offering])
        self.assertEqual(self.offering.slot_kinds, [])
        self.assertFalse(apply_kind_filter(CourseOffering.objects.all(), "seminar").exists())
        self.assertEqual(journal_window.kind_tabs(self.offering, "seminar"), [])

    def test_selected_label_and_multi_group_units_do_not_multiply_kinds(self):
        other = make_structure(self.org, code="JPK4")
        self.row.groups.add(other["group"])
        self.row.subgroup_count = 2
        self.row.seminar_total = 30
        self.row.save(update_fields=["subgroup_count", "seminar_total"])
        attach_kind_labels([self.offering], "seminar")
        self.assertEqual(self.offering.slot_kinds, ["lecture", "seminar", "lab"])
        self.assertNotIn("·", self.offering.kind_label)

    def test_offering_without_group_does_not_inherit_other_groups_plan(self):
        offering = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=None
        )
        attach_kind_labels([offering])
        self.assertEqual(offering.slot_kinds, [])
        self.assertEqual(journal_window.kind_tabs(offering, ""), [])
        self.assertFalse(apply_kind_filter(CourseOffering.objects.filter(pk=offering.pk), "seminar").exists())
