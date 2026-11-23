"""Sahib 2026-11-23: intensiv açılış yerində qrupun öz açılışına çevrilir (``convert_intensive_to_group_20261123``)."""

from __future__ import annotations

import pathlib
from collections import Counter
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import Membership
from apps.registrar import intensive_to_group_2026_11_23 as fixer
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, StudentAcademicRecord, Subject
from apps.registrar.models.offering_format import CourseFormat
from apps.workload.constants import RowKind
from apps.workload.models import TeachingTaskRow
from apps.workload.tests.factories import make_org, make_structure, make_task
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class SpecTest(SimpleTestCase):
    def test_fixed_ids(self):
        self.assertTrue(fixer.OFFERING_ID.startswith("95c97c37-"))
        self.assertTrue(fixer.ROW_ID.startswith("5b11525f-"))
        self.assertTrue(fixer.GROUP_ID.startswith("ecd6b7f1-"))

    def test_workflow_runs_the_command(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - convert_intensive_to_group_20261123\n", text)
        self.assertIn("            convert_intensive_to_group_20261123)\n", text)
        self.assertIn('[ "$COMMAND" = "convert_intensive_to_group_20261123" ]', text)
        self.assertIn("|intgrp|", text)


class IntensiveToGroupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("intgrp")
            cls.stack = make_structure(cls.org, code="IG")
            cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
            cls.actor = get_user_model().objects.create_superuser("intgrp_admin", "intgrp@qku.edu.az", "pw")
            cls.subject = Subject.objects.create(organization=cls.org, code="IG202", name="Psixogenetika", ects=3)
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.subject,
                period=cls.stack["period"],
                course_format=CourseFormat.INTENSIVE,
                starts_on=date(2026, 11, 19),
                ends_on=date(2027, 1, 31),
                lesson_hours=20,
            )
            cls.row = TeachingTaskRow.objects.create(
                organization=cls.org,
                task=cls.task,
                season="fall",
                period=cls.stack["period"],
                subject=cls.subject,
                row_kind=RowKind.INTENSIVE,
                lecture_plan=10,
                lecture_total=10,
                seminar_plan=10,
                seminar_total=10,
                total_hours=20,
                intensive_offering=cls.offering,
            )
            cls.curriculum = Curriculum.objects.create(
                organization=cls.org, program=cls.stack["program"], admission_year=2023
            )
            cls.enrollments = []
            for index in range(3):
                student = get_user_model().objects.create_user(f"intgrp_s{index}", f"intgrp_s{index}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=cls.stack["program"],
                    curriculum=cls.curriculum,
                    group=cls.stack["group"],
                    admission_year=2023,
                )
                cls.enrollments.append(
                    Enrollment.objects.create(
                        organization=cls.org,
                        offering=cls.offering,
                        student=student,
                        source_group=cls.stack["group"],
                    )
                )

    def setUp(self):
        scope = bypass_rls()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        for name, value in (
            ("OFFERING_ID", str(self.offering.pk)),
            ("ROW_ID", str(self.row.pk)),
            ("GROUP_ID", str(self.stack["group"].pk)),
        ):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_fix(self):
        counts = Counter()
        batch = fixer.run(organization=self.org, actor=self.actor, counts=counts, batch="")
        return counts, batch

    def test_moves_students_to_new_group_offering_and_undo_restores(self):
        counts, batch = self.run_fix()
        self.assertEqual(counts["group_offering_created"], 1)
        self.assertEqual(counts["students_moved"], 3)
        target = CourseOffering.objects.get(subject=self.subject, group=self.stack["group"])
        self.assertEqual(target.course_format, CourseFormat.REGULAR)
        self.assertEqual(
            Enrollment.objects.filter(offering=target, status="enrolled", source_group__isnull=True).count(), 3
        )
        self.offering.refresh_from_db()
        self.row.refresh_from_db()
        self.assertFalse(self.offering.is_active)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 0)
        self.assertEqual(self.row.row_kind, RowKind.TEACHING)
        self.assertIsNone(self.row.intensive_offering_id)
        self.assertEqual(list(self.row.groups.values_list("pk", flat=True)), [self.stack["group"].pk])
        again, _ = self.run_fix()
        self.assertEqual(again["already_converted"], 1)
        undone = Counter()
        fixer.undo(organization=self.org, actor=self.actor, counts=undone, batch=batch)
        self.assertEqual(undone["undone"], 1)
        self.offering.refresh_from_db()
        self.row.refresh_from_db()
        target.refresh_from_db()
        self.assertTrue(self.offering.is_active)
        self.assertFalse(target.is_active)
        self.assertEqual(self.row.intensive_offering_id, self.offering.pk)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 3)
        self.assertEqual(Enrollment.objects.filter(offering=target).count(), 0)

    def test_refuses_when_group_offering_already_exists(self):
        CourseOffering.objects.create(
            organization=self.org, subject=self.subject, period=self.stack["period"], group=self.stack["group"]
        )
        counts, _ = self.run_fix()
        self.assertEqual(counts["group_offering_exists"], 1)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.course_format, CourseFormat.INTENSIVE)
