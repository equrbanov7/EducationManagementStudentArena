"""Real PostgreSQL: retain106cells/15lessons/15enrollments and rebind one subject only."""

import datetime as dt
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark, Subject
from apps.syllabus.public import content_fingerprints, import_migrated_version
from apps.workload.services import reviewed_ilahe_subject_state as actor_state
from apps.workload.services import reviewed_jale_subject_repair as repair
from apps.workload.services import reviewed_jale_subject_spec as spec
from apps.workload.services import reviewed_jale_subject_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_structure

User = get_user_model()


class ReviewedJaleSubjectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("jale-rebind")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save(update_fields=["is_superuser"])
        apps.get_model("accounts.UserProfile").objects.filter(user=cls.actor).update(
            organization=cls.org, access_state="active"
        )
        cls.teacher = User.objects.create_user("jale-lifelong-preserved", first_name="Jalə", last_name="Qəniyeva")
        cls.other = User.objects.create_user("jale-separate-preserved", first_name="Jalə", last_name="Qəniyeva")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        cls.stack = make_structure(cls.org, code="JS")
        cls.old = Subject.objects.create(organization=cls.org, code="WRONG1797", name="Wrong computer printing")
        cls.new = cls.stack["subject"]
        cls.courses = []
        for i in range(4):
            group = (
                cls.stack["group"]
                if i == 0
                else apps.get_model("organizations.OrgUnit").objects.create(
                    organization=cls.org,
                    parent=cls.stack["specialty"],
                    unit_type="group",
                    name=f"Foreign{i}",
                    slug=f"foreign-{i}",
                )
            )
            course = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.old if i == 0 else cls.new,
                period=cls.stack["period"],
                group=group,
                instructor=None,
                lesson_hours=150,
            )
            cls.courses.append(course)
            JournalShare.objects.create(
                organization=cls.org, offering=course, teacher=cls.teacher, kinds=[], source="legacy"
            )
        enrs = []
        for i in range(15):
            student = User.objects.create_user(f"jale-enrolled-{i}")
            activate_member(cls.org, student, "student", permissions=["course.view", "grade.view"])
            enrs.append(Enrollment.objects.create(organization=cls.org, offering=cls.courses[0], student=student))
        marks = []
        for i in range(15):
            lesson = Lesson.objects.create(
                organization=cls.org,
                offering=cls.courses[0],
                date=dt.date(2026, 9, 1) + dt.timedelta(days=i),
                kind="seminar",
                hours=2,
                topic="Preserve actual language topic",
            )
            for j, enr in enumerate(enrs):
                if i < 7 or i == 7 and j == 0:
                    marks.append(
                        LessonMark(
                            organization=cls.org,
                            lesson=lesson,
                            enrollment=enr,
                            status="absent" if j == 1 else "present",
                            score=Decimal("0") if j == 0 else None,
                        )
                    )
        LessonMark.objects.bulk_create(marks)
        cls.source, cls.version = import_migrated_version(
            organization=cls.org,
            subject=cls.new,
            offering=cls.courses[1],
            period=cls.stack["period"],
            author=None,
            approved_at=timezone.now(),
            section_data={"week": {"rows": [{"topic": f"Own language topic{i}", "practical": 2} for i in range(120)]}},
        )

    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        pins = {
            "ORG": str(self.org.pk),
            "TARGET": str(self.courses[0].pk),
            "GROUP": str(self.courses[0].group_id),
            "PERIOD": str(self.stack["period"].pk),
            "OLD_SUBJECT": str(self.old.pk),
            "NEW_SUBJECT": str(self.new.pk),
            "TEACHER": self.teacher.pk,
            "SEPARATE_ACCOUNT": self.other.pk,
            "SOURCE_SYLLABUS": str(self.source.pk),
            "SOURCE_VERSION": str(self.version.pk),
            "SOURCE_BODY_SHA": content_fingerprints({s.section_id: s.data for s in self.version.sections.all()})[
                "canonical_body_sha256"
            ],
            "OFFERINGS": {str(c.pk): str(c.group_id) for c in self.courses},
        }
        for k, v in pins.items():
            self.patches.enter_context(patch.object(spec, k, v))
        self.patches.enter_context(patch.object(actor_state.spec, "ORG", str(self.org.pk)))
        self.patches.enter_context(patch.object(state, "_bridge", return_value={"count": 1, "sha256": "a" * 64}))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def test_apply_repeat_undo_preserve_exact_graph_and_accounts(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        applied = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["status"], "applied")
        self.courses[0].refresh_from_db()
        self.assertEqual(self.courses[0].subject_id, self.new.pk)
        self.assertEqual(self.courses[0].lesson_hours, 150)
        after = state.snapshot(self.org)
        self.assertEqual(repair.protected(before), repair.protected(after))
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.courses[0]).count(), 106)
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.courses[0], score=Decimal("0")).count(), 8)
        self.assertEqual(self.run_repair()["receipt"], applied["receipt"])
        undry = self.run_repair(undo=applied["receipt"])
        undo = self.run_repair(apply=True, undo=applied["receipt"], expected_baseline=undry["baseline"])
        self.assertEqual(undo["status"], "undone")
        self.assertEqual(state.snapshot(self.org), before)
        self.assertEqual(self.run_repair(undo=applied["receipt"])["status"], "already_undone")

    def test_stale_baseline_and_unreviewed_target_syllabus_stop_before_write(self):
        with self.assertRaises(RepairError):
            self.run_repair(apply=True, expected_baseline="0" * 64)
        self.courses[0].refresh_from_db()
        self.assertEqual(self.courses[0].subject_id, self.old.pk)
        import_migrated_version(
            organization=self.org,
            subject=self.old,
            offering=self.courses[0],
            period=self.stack["period"],
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Human/own target must be separately reviewed"}},
        )
        with self.assertRaisesRegex(RepairError, "target_content"):
            self.run_repair()

    def test_body_changed_actor_outside_org_and_new_subject_collision_stop(self):
        with patch.object(spec, "SOURCE_BODY_SHA", "0" * 64):
            with self.assertRaisesRegex(RepairError, "source_body_changed"):
                self.run_repair()
        actor = User.objects.create_user("jale-outsider", is_superuser=True)
        with self.assertRaises(RepairError):
            repair.run(organization=self.org, actor=actor)
        CourseOffering.objects.create(
            organization=self.org, subject=self.new, period=self.stack["period"], group=self.courses[0].group
        )
        with self.assertRaisesRegex(RepairError, "collision"):
            self.run_repair()

    def test_postwrite_failure_rolls_back_and_clears_existing_exception(self):
        dry = self.run_repair()
        before = state.snapshot(self.org)
        with patch.object(state, "snapshot", side_effect=[before, RepairError("jale_preservation_failed")]):
            with patch.object(
                repair.subject_merge_apply,
                "clear_offering_subject_change",
                wraps=repair.subject_merge_apply.clear_offering_subject_change,
            ) as clear:
                with self.assertRaises(RepairError):
                    self.run_repair(apply=True, expected_baseline=dry["baseline"])
                self.assertEqual(clear.call_count, 1)
        self.courses[0].refresh_from_db()
        self.assertEqual(self.courses[0].subject_id, self.old.pk)
        self.assertFalse(apps.get_model("audit.AuditLog").objects.filter(resource_type=repair.RESOURCE).exists())

    def test_counts_drift_and_unreceipted_corrected_state_are_refused(self):
        with patch.dict(spec.COUNTS, {"registrar.LessonMark": 107}):
            with self.assertRaisesRegex(RepairError, "counts_changed"):
                self.run_repair()
        dry = self.run_repair()
        applied = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        audit = apps.get_model("audit.AuditLog").objects.get(
            resource_type=repair.RESOURCE, resource_id=applied["receipt"]
        )
        # Do not delete immutable audit rows: hide this receipt from the service instead.
        with patch.object(repair, "RESOURCE", repair.RESOURCE + ".unreceipted"):
            with self.assertRaisesRegex(RepairError, "without_receipt"):
                self.run_repair()
        self.assertEqual(audit.resource_id, applied["receipt"])
