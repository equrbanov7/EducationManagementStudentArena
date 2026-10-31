"""A mistaken catalogue FK must not erase modelling lessons, scores or own authorship."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.public import import_migrated_version, section_data_map, syllabus_for_offering
from apps.workload.models import TeacherAssignment
from apps.workload.services import qosqar_modelling_repair as service
from apps.workload.tests import test_scoped_snapshot as fixtures


class QosqarModellingTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.task.status = "distributed"
        self.task.save()
        self.stack["subject"].code = "QKU-868"
        self.stack["subject"].save()
        old = Subject.objects.create(organization=self.org, code="QKU-1797", name="Printing")
        duplicate = Subject.objects.create(organization=self.org, code="QKU-1487", name="Modelling alternative")
        group = OrgUnit.objects.create(
            organization=self.org, name="233 IT", slug="233-it", unit_type="group", parent=self.stack["specialty"]
        )
        self.row.groups.set([group])
        self.row.subject = old
        self.row.subject_text = "Printing from mistaken catalogue"
        self.row.lecture_total = self.row.seminar_total = 45
        self.row.lecture_plan = self.row.seminar_plan = 45
        self.row.lab_total = self.row.lab_plan = 0
        self.row.total_hours = 90
        self.row.save()
        for activity in ("lecture", "seminar"):
            TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=self.teacher, activity=activity, hours=45
            )
        fixtures.activate_member(self.org, self.actor, "student")
        self.offerings = []
        for subject, offering_group in ((old, group), (duplicate, group), (self.stack["subject"], self.stack["group"])):
            o = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                group=offering_group,
                period=self.stack["period"],
                instructor=self.teacher,
                lesson_hours=90,
            )
            Enrollment.objects.create(organization=self.org, offering=o, student=self.actor)
            self.offerings.append(o)
        target, empty, anchor = self.offerings
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=target,
            date="2026-10-13",
            start_time="13:35",
            kind="seminar",
            topic="Computer modelling",
        )
        self.mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=target.enrollments.first(), status="present", score=8
        )
        self.sections = {"desc": {"description": "Own original computer modelling syllabus"}}
        syllabus, version = import_migrated_version(
            organization=self.org,
            subject=anchor.subject,
            period=anchor.period,
            offering=anchor,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data=self.sections,
        )
        self.sections = section_data_map(version)
        self.syllabus, self.version = syllabus, version
        values = {
            "ORG": str(self.org.pk),
            "TASK": str(self.task.pk),
            "PERIOD": str(anchor.period_id),
            "TEACHER": self.teacher.pk,
            "OFFERING": str(target.pk),
            "EMPTY": str(empty.pk),
            "ANCHOR": str(anchor.pk),
            "ROW": str(self.row.pk),
            "GROUP": str(group.pk),
            "OLD": str(old.pk),
            "NEW": str(anchor.subject_id),
            "ALTERNATE": str(duplicate.pk),
            "SYLLABUS": str(syllabus.pk),
            "VERSION": str(version.pk),
            "SOURCE_CONTENT_SHA": service.digest(self.sections),
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for key, value in values.items():
            self.patches.enter_context(patch.object(service, key, value))
        self.patches.enter_context(patch.object(service.common, "ORG", str(self.org.pk)))
        self.patches.enter_context(patch.object(service.common, "GROUP", str(anchor.group_id)))

    def call(self, **kwargs):
        return service.repair_qosqar_modelling(
            organization=self.org, user=self.actor, sections=self.sections, source_sha256=service.SOURCE_SHA, **kwargs
        )

    def test_correction_share_repeat_and_undo_preserve_all_historical_ids(self):
        self.prepare()
        before = service.capture()
        dry = self.call()
        self.assertEqual(service.digest(before), service.digest(service.capture()))
        self.call(apply=True, expected_baseline=dry["baseline"])
        target, empty, anchor = self.offerings
        target.refresh_from_db()
        empty.refresh_from_db()
        self.assertEqual(target.subject_id, anchor.subject_id)
        self.assertFalse(empty.is_active)
        effective = syllabus_for_offering(
            organization=self.org,
            offering_id=target.pk,
            subject_id=target.subject_id,
            period_id=target.period_id,
            instructor_id=self.teacher.pk,
        )
        self.assertEqual(effective.pk, self.syllabus.pk)
        self.assertEqual(effective.author_id, self.teacher.pk)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 8)
        self.assertEqual(self.call()["already_present"], 1)
        self.assertEqual(
            service.digest(service.protected(before)), service.digest(service.protected(service.capture()))
        )
        dry_undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=dry_undo["baseline"])
        final = service.capture()
        self.assertEqual(service.digest(before["academic"]), service.digest(final["academic"]))
        self.assertEqual(service.digest(before["assignments"]), service.digest(final["assignments"]))

    def test_changed_current_own_content_aborts(self):
        self.prepare()
        section = self.version.sections.get(section_id="desc")
        section.data = {"description": "Teacher changed this after the source snapshot"}
        section.save()
        with self.assertRaisesMessage(service.ModellingError, "own_approved_source6591_content_changed"):
            self.call()

    def test_other_authors_syllabus_is_never_shared(self):
        self.prepare()
        self.syllabus.author = self.actor
        self.syllabus.save()
        with self.assertRaisesMessage(service.ModellingError, "own_approved_syllabus_identity_changed"):
            self.call()

    def test_live_mark_edit_blocks_undo(self):
        self.prepare()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.mark.score = 9
        self.mark.save()
        with self.assertRaisesMessage(service.ModellingError, "undo_live_state_changed"):
            self.call(undo=True)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 9)

    def test_competing_empty_offering_now_has_content_aborts(self):
        self.prepare()
        Lesson.objects.create(organization=self.org, offering=self.offerings[1], date="2026-10-13", kind="lecture")
        with self.assertRaisesMessage(service.ModellingError, "empty_offering_has_content"):
            self.call()

    def test_share_conflict_rolls_back_subject_row_and_every_existing_cell(self):
        self.prepare()
        before = service.digest(service.capture())
        dry = self.call()
        with patch.object(service, "link_legacy_share", return_value="taken"):
            with self.assertRaisesMessage(service.ModellingError, "own_syllabus_fill_only_share_failed"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(before, service.digest(service.capture()))
