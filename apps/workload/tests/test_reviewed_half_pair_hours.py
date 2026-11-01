"""Migrated PG: hours correction preserves raw scores/i/e/credits; exact undo keeps partial clocks."""

import datetime as dt
import io
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from apps.organizations.models import OrgUnit
from apps.registrar.models import AbsenceCredit, AssessmentScheme, CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.models import TeacherAssignment
from apps.workload.services import four_cell_recovery_history as actors
from apps.workload.services import reviewed_half_pair_repair as service
from apps.workload.services import reviewed_half_pair_spec as spec
from apps.workload.services.sbio235_state import RepairError
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import apply_rls_request_context, bypass_rls, reset_rls_context

User = get_user_model()


class HalfPairHoursTests(TransactionTestCase):
    def setUp(self):
        with bypass_rls():
            self.org = make_org("half-pair")
            self.actor = User.objects.create_superuser("half-pair-operator", password="x")
            activate_member(self.org, self.actor, "rector")
            self.teacher = User.objects.create_user("half-pair-teacher")
            activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS)
            self.stack = make_structure(self.org, code="HALFPAIR")
            self.task = make_task(self.org, self.stack["chair"])
            self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
            self.assignment = TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=15
            )
            self.lessons = []
            self.enrs = []
            cases = []
            for index in range(2):
                group = (
                    self.stack["group"]
                    if index == 0
                    else OrgUnit.objects.create(
                        organization=self.org,
                        parent=self.stack["specialty"],
                        unit_type="group",
                        slug="half-other",
                        name="Other",
                    )
                )
                offering = CourseOffering.objects.create(
                    organization=self.org,
                    subject=self.stack["subject"],
                    period=self.stack["period"],
                    group=group,
                    instructor=self.teacher,
                    lesson_hours=45,
                )
                AssessmentScheme.objects.create(organization=self.org, offering=offering)
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=offering,
                    date="2026-10-15",
                    start_time="15:15",
                    hours=2,
                    kind="seminar",
                    topic="Verified source",
                )
                student = User.objects.create_user("half-student-" + str(index))
                activate_member(self.org, student, "student", permissions=["course.view"])
                enr = Enrollment.objects.create(
                    organization=self.org, student=student, offering=offering, absence_hours=2 if index == 0 else 0
                )
                mark = LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enr,
                    status="absent" if index == 0 else "excused",
                    score=None if index == 0 else Decimal("0"),
                    entered_by=self.teacher,
                )
                lesson.refresh_from_db()
                self.lessons.append(lesson)
                self.enrs.append(enr)
                cases.append(
                    {
                        "offering": {
                            "id": str(offering.pk),
                            "group_id": str(group.pk),
                            "subject_id": str(offering.subject_id),
                            "period_id": str(offering.period_id),
                            "instructor_id": self.teacher.pk,
                            "is_active": True,
                            "lesson_hours": 45,
                        },
                        "lesson": {
                            "id": str(lesson.pk),
                            "offering_id": str(offering.pk),
                            "date": "2026-10-15",
                            "start_time": "15:15:00",
                            "end_time": None,
                            "kind": "seminar",
                            "created_by_id": None,
                            "instructor_id": None,
                            "room_id": None,
                            "syllabus_week": None,
                            "topic": "Verified source",
                            "is_legacy_synthesised": False,
                        },
                        "marks": [(str(mark.pk), str(enr.pk), mark.status, mark.score, mark.entered_by_id)],
                    }
                )
            self.row.groups.set([lesson.offering.group for lesson in self.lessons])
            self.raw = list(LessonMark.objects.filter(organization=self.org).order_by("pk").values())
        self.cases = cases
        self.actor.set_active_organization_context(self.org)
        self.patcher = patch.multiple(
            spec,
            ORG=str(self.org.pk),
            CASES=cases,
            ROW=str(self.row.pk),
            ASSIGNMENTS={str(self.assignment.pk): (self.teacher.pk, "seminar", 15, False)},
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.actor_patch = patch.object(actors, "ORG", str(self.org.pk))
        self.actor_patch.start()
        self.addCleanup(self.actor_patch.stop)
        self.addCleanup(reset_rls_context)

    def invoke(self, **kwargs):
        with transaction.atomic():
            apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
            return service.repair(organization=self.org, actor=self.actor, **kwargs)

    def test_apply_repeat_undo_preserves_raw_and_partial_clocks(self):
        before = self.invoke()
        self.assertEqual(before["derived_after"], 1)
        applied = self.invoke(apply=True, expected_baseline=before["baseline"])
        repeat = self.invoke()
        self.assertEqual(repeat["status"], "already_present")
        self.assertEqual(self.invoke(apply=True, expected_baseline=repeat["baseline"])["lessons_changed"], 0)
        undone = self.invoke(undo=applied["receipt"])
        self.assertEqual(undone["status"], "dry_run")
        self.invoke(undo=applied["receipt"], apply=True, expected_baseline=undone["baseline"])
        self.assertEqual(self.invoke(undo=applied["receipt"])["status"], "already_undone")
        with bypass_rls():
            self.assertEqual(list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), self.raw)
            for lesson in self.lessons:
                lesson.refresh_from_db()
                self.assertEqual((lesson.hours, lesson.start_time, lesson.end_time), (2, dt.time(15, 15), None))

    def test_credit_and_stale_cache_are_preserved_with_canonical_reconciliation(self):
        with bypass_rls():
            AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=self.enrs[0],
                hours=1,
                request_token=uuid4(),
                reason="Existing approved credit evidence",
                actor=self.actor,
                old_absence_hours=2,
                new_absence_hours=1,
            )
            original = list(AbsenceCredit.objects.values())
            Enrollment.objects.filter(pk=self.enrs[0].pk).update(absence_hours=0)
        dry = self.invoke()
        self.assertEqual((dry["cached_before"], dry["derived_before"], dry["derived_after"]), (0, 1, 0))
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            self.enrs[0].refresh_from_db()
            self.assertEqual(self.enrs[0].absence_hours, 0)
            self.assertEqual(list(AbsenceCredit.objects.values()), original)
        undo = self.invoke(undo=applied["receipt"])
        self.invoke(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        with bypass_rls():
            self.enrs[0].refresh_from_db()
            self.assertEqual(self.enrs[0].absence_hours, 1)
            self.assertEqual(list(AbsenceCredit.objects.values()), original)

    def test_late_credit_blocks_baseline_and_undo(self):
        dry = self.invoke()
        with bypass_rls():
            AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=self.enrs[0],
                hours=1,
                request_token=uuid4(),
                reason="New approved credit evidence",
                actor=self.actor,
                old_absence_hours=2,
                new_absence_hours=1,
            )
        with self.assertRaises(RepairError):
            self.invoke(apply=True, expected_baseline=dry["baseline"])

    def test_receipt_from_changed_source_scope_is_not_adopted(self):
        dry = self.invoke()
        self.invoke(apply=True, expected_baseline=dry["baseline"])
        with patch.object(spec, "SOURCE_PROOF_SHA", "b" * 64), self.assertRaises(RepairError):
            self.invoke()

    def test_later_credit_after_apply_blocks_undo_without_raw_mutation(self):
        dry = self.invoke()
        applied = self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=self.enrs[0],
                hours=1,
                request_token=uuid4(),
                reason="Later approved credit evidence",
                actor=self.actor,
                old_absence_hours=1,
                new_absence_hours=0,
            )
        with self.assertRaises(RepairError):
            self.invoke(undo=applied["receipt"])
        with bypass_rls():
            self.assertEqual(list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), self.raw)
            self.assertEqual(
                set(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons]).values_list("hours", flat=True)), {1}
            )

    def test_failure_after_first_correction_rolls_back_raw_caches_and_evidence(self):
        dry = self.invoke()
        real = service.apply_lesson_correction
        calls = []

        def fail(**kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("injected")
            return real(**kwargs)

        with patch.object(service, "apply_lesson_correction", side_effect=fail), self.assertRaises(ValueError):
            self.invoke(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.invoke()["baseline"], dry["baseline"])

    def test_changed_mark_refused(self):
        with bypass_rls():
            LessonMark.objects.filter(pk=self.raw[0]["id"]).update(status="present")
        with self.assertRaises(RepairError):
            self.invoke()

    def test_actual_readonly_command_both_rls_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text("fixed source evidence")
            path.chmod(0o600)
            import hashlib

            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(spec, "SOURCE_PROOF_SHA", digest):
                for mode in (False, True):
                    with override_settings(RLS_TRANSACTION_SCOPED=mode):
                        out = io.StringIO()
                        call_command(
                            "repair_reviewed_half_pair_hours",
                            actor=self.actor.username,
                            org=self.org.slug,
                            file=str(path),
                            sha256=digest,
                            stdout=out,
                        )
                        result = json.loads(out.getvalue().split(": ", 1)[1])
                        self.assertEqual(result["status"], "dry_run")
                        self.assertEqual(result["derived_after"], 1)
            self.assertEqual(self.invoke()["status"], "dry_run")

    def test_reversed_credit_and_exact_successor_are_retained(self):
        with bypass_rls():
            old = self.enrs[0]
            group = OrgUnit.objects.create(
                organization=self.org,
                parent=self.stack["specialty"],
                unit_type="group",
                slug="half-successor",
                name="Successor",
            )
            course = CourseOffering.objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                group=group,
                instructor=self.teacher,
                lesson_hours=45,
            )
            target = Enrollment.objects.create(
                organization=self.org, student=old.student, offering=course, absence_hours=4
            )
            old.status = "dropped"
            old.superseded_by = target
            old.save(update_fields=["status", "superseded_by"])
            lesson = Lesson.objects.create(
                organization=self.org, offering=course, date="2026-10-16", hours=2, kind="seminar"
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=target, status="absent")
            root = AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=old,
                hours=1,
                request_token=uuid4(),
                reason="Existing valid approved credit",
                actor=self.actor,
                old_absence_hours=2,
                new_absence_hours=1,
            )
            AbsenceCredit.objects.create(
                organization=self.org,
                enrollment=old,
                hours=1,
                request_token=uuid4(),
                reason="Existing valid reversed credit",
                actor=self.actor,
                reverses=root,
                old_absence_hours=1,
                new_absence_hours=2,
            )
            credits = list(AbsenceCredit.objects.values())
        dry = self.invoke()
        self.invoke(apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            target.refresh_from_db()
            old.refresh_from_db()
            self.assertEqual((old.absence_hours, target.absence_hours), (1, 3))
            self.assertEqual(list(AbsenceCredit.objects.values()), credits)

    def test_actual_command_full_36_marks_cap_apply_and_undo(self):
        with bypass_rls():
            for index, count in enumerate((16, 18)):
                for offset in range(count):
                    student = User.objects.create_user(f"half-full-{index}-{offset}")
                    activate_member(self.org, student, "student", permissions=["course.view"])
                    enr = Enrollment.objects.create(
                        organization=self.org, student=student, offering=self.lessons[index].offering
                    )
                    mark = LessonMark.objects.create(
                        organization=self.org, lesson=self.lessons[index], enrollment=enr, status="present"
                    )
                    self.cases[index]["marks"].append((str(mark.pk), str(enr.pk), "present", None, None))
            raw = list(LessonMark.objects.filter(organization=self.org).order_by("pk").values())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text("fixed full36 evidence")
            path.chmod(0o600)
            import hashlib

            token = hashlib.sha256(path.read_bytes()).hexdigest()

            def command(**kwargs):
                out = io.StringIO()
                call_command(
                    "repair_reviewed_half_pair_hours",
                    actor=self.actor.username,
                    org=self.org.slug,
                    file=str(path),
                    sha256=token,
                    stdout=out,
                    **kwargs,
                )
                return json.loads(out.getvalue().split(": ", 1)[1])

            with patch.object(spec, "SOURCE_PROOF_SHA", token):
                dry = command()
                applied = command(apply=True, baseline=dry["baseline"])
                repeated = command()
                self.assertEqual(repeated["status"], "already_present")
                done = command(apply=True, baseline=repeated["baseline"])
                self.assertEqual(done["lessons_changed"], 0)
                undo = command(undo=applied["receipt"])
                command(undo=applied["receipt"], apply=True, baseline=undo["baseline"])
        with bypass_rls():
            self.assertEqual(list(LessonMark.objects.filter(organization=self.org).order_by("pk").values()), raw)

    def test_foreign_superadmin_cannot_read_or_apply(self):
        outsider = User.objects.create_superuser("half-outsider", password="x")
        with transaction.atomic(), self.assertRaises(ValueError):
            service.repair(organization=self.org, actor=outsider)


@override_settings(RLS_TRANSACTION_SCOPED=True)
class HalfPairHoursTransactionScopedTests(HalfPairHoursTests):
    pass
