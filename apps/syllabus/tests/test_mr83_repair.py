"""Real database checks for exact dossier replacement and compensating undo."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.syllabus.public import import_migrated_version
from apps.syllabus.services import mr83_repair as service
from apps.workload.tests import test_scoped_snapshot as fixtures


class MR83RepairTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        values = {
            "SUBJECT": str(self.stack["subject"].pk),
            "PERIOD": str(self.stack["period"].pk),
            "TEACHER": self.teacher.pk,
        }
        for index, count in enumerate((8, 23)):
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                instructor=self.teacher,
                group=self.stack["group"] if index == 0 else None,
            )
            syllabus, version = import_migrated_version(
                organization=self.org,
                subject=offering.subject,
                period=offering.period,
                offering=offering,
                author=self.teacher,
                approved_at=timezone.now(),
                section_data={"week": {"rows": [{"topic": f"Proven topic {i}", "lecture": 2} for i in range(count)]}},
            )
            values["TARGET" if index == 0 else "SOURCE_OFFERING"] = str(offering.pk)
            values["OLD" if index == 0 else "SOURCE"] = str(syllabus.pk)
            values["OLD_VERSION" if index == 0 else "SOURCE_VERSION"] = str(version.pk)
        fixtures.activate_member(self.org, self.actor, "student")
        enrollment = Enrollment.objects.create(organization=self.org, offering_id=values["TARGET"], student=self.actor)
        lesson = Lesson.objects.create(
            organization=self.org, offering_id=values["TARGET"], date="2026-10-22", kind="seminar"
        )
        LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status="present", score=9
        )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for key, value in values.items():
            self.patches.enter_context(patch.object(service, key, value))

    def call(self, **kwargs):
        return service.repair_mr83_syllabus(organization=self.org, user=self.actor, **kwargs)

    def test_dry_apply_repeat_and_undo_preserve_versions(self):
        self.prepare()
        before = service.digest(service.protected(service.capture()))
        dry = self.call()
        self.assertFalse(service.model("syllabus.SyllabusShare").objects.filter(offering_id=service.TARGET).exists())
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.call()["already_present"], 1)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertTrue(service.model("syllabus.Syllabus").objects.get(pk=service.OLD).is_active)
        self.assertEqual(before, service.digest(service.protected(service.capture())))

    def test_failed_link_rolls_back_dossier(self):
        self.prepare()
        dry = self.call()
        with patch.object(service, "link_legacy", return_value="taken"):
            with self.assertRaisesMessage(service.MR83Error, "canonical_share_failed"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(service.model("syllabus.Syllabus").objects.get(pk=service.OLD).is_active)

    def test_stale_baseline_refuses(self):
        self.prepare()
        with self.assertRaisesMessage(service.MR83Error, "live_baseline_changed"):
            self.call(apply=True, expected_baseline="0" * 64)

    def test_undo_refuses_new_teacher_data(self):
        self.prepare()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        Lesson.objects.create(organization=self.org, offering_id=service.TARGET, date="2026-10-29", kind="seminar")
        with self.assertRaisesMessage(service.MR83Error, "undo_live_state_changed"):
            self.call(undo=True)
