"""Real PostgreSQL regressions for two reviewed historical attendance conflicts."""

import copy
import datetime as dt
import hashlib
import json
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.versioning import ensure_initial_version
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import reaudit_journal_structure as op
from apps.registrar import reaudit_journal_structure_spec as spec
from apps.registrar import reaudit_journal_structure_state as state
from apps.registrar.models import CourseOffering, Enrollment, JournalCorrection, Lesson, LessonMark
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from core.reviewed_graph import rows
from core.rls import journal_unlock


class OwnerPresentConflictTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering

    def setUp(self):
        self.actor = self.org.owner
        self.actor.profile.organization = self.org
        self.actor.profile.access_state = "active"
        self.actor.profile.save()
        self.source = self.offering(instructor=self.teacher)
        CourseOffering.objects.filter(pk=self.source.pk).update(is_active=False)
        self.source.refresh_from_db()
        group = OrgUnit.objects.create(
            organization=self.org, name="Synthetic conflict target", slug="conflict-target", unit_type="group"
        )
        self.target = CourseOffering.objects.create(
            organization=self.org,
            subject=self.source.subject,
            period=self.source.period,
            group=group,
            instructor=self.teacher,
        )
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.source,
            instructor=self.teacher,
            date=dt.date(2026, 9, 22),
            start_time=dt.time(9),
            end_time=dt.time(10, 30),
            kind="lecture",
            hours=2,
        )
        self.source_enrollments, self.targets, self.marks = [], [], []
        self.run_record = create_run(
            actor=self.actor,
            authorize=lambda **kw: True,
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=8,
            schema_version="fixture",
            transform_version="fixture",
            mode="rehearsal",
        )
        self.run_record = start_run(run_id=self.run_record.pk, actor=self.actor, authorize=lambda **kw: True)
        for entity, legacy, label, target in (
            ("lesson_subject", "501", "registrar.subject", self.source.subject_id),
            ("worker", "601", "auth.user", self.teacher.pk),
            ("group_unit", "701", "organizations.orgunit", self.source.group_id),
            ("group_unit", "702", "organizations.orgunit", group.pk),
        ):
            self.mapping(entity, legacy, label, target)
        for index in range(2):
            user = get_user_model().objects.create_user(f"conflict-synthetic-{index}")
            Membership.objects.create(
                organization=self.org, user=user, role=self.org.roles.get(name="student"), is_active=True
            )
            target = Enrollment.objects.create(organization=self.org, offering=self.target, student=user)
            source = Enrollment.objects.create(
                organization=self.org,
                offering=self.source,
                student=user,
                status="dropped",
                superseded_by=target,
                absence_hours=2,
            )
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.lesson,
                enrollment=source,
                status="absent",
                entered_by=self.teacher,
            )
            Enrollment.objects.filter(pk=target.pk).update(absence_hours=2)
            self.source_enrollments.append(source)
            self.targets.append(target)
            self.marks.append(mark)
            self.mapping("student", str(801 + index), "auth.user", user.pk)
        zero_lesson = Lesson.objects.create(
            organization=self.org, offering=self.source, date=dt.date(2026, 10, 1), kind="seminar", hours=2
        )
        self.zero = LessonMark.objects.create(
            organization=self.org,
            lesson=zero_lesson,
            enrollment=self.source_enrollments[0],
            status="present",
            score=0,
            entered_by=self.other,
        )
        self.authority_value = {
            "format": "reaudit-owner-present-conflict/1",
            "organization_id": str(self.org.pk),
            "period_id": str(self.source.period_id),
            "source_system": "myedu_mariadb",
            "source_sha256": "a" * 64,
            "decision_policy": "owner-present-for-exact-legacy-target-conflict-20261109",
            "source": {
                "journals": [self.header(101, "conflict-source", 701), self.header(102, "conflict-target", 702)],
                "points": [],
                "excuse_windows": [],
            },
            "cases": [],
        }
        for index, mark in enumerate(self.marks):
            self.authority_value["source"]["points"].extend(
                [
                    self.point(901 + index, 801 + index, "conflict-source", "qb"),
                    self.point(911 + index, 801 + index, "conflict-target", "ie"),
                ]
            )
            pins = rows(LessonMark.objects.filter(pk=mark.pk))[0]
            fields = (
                "id",
                "organization_id",
                "lesson_id",
                "enrollment_id",
                "status",
                "score",
                "entered_by_id",
                "created_at",
                "updated_at",
            )
            self.authority_value["cases"].append(
                {
                    "source_mark_id": str(mark.pk),
                    "source_enrollment_id": str(mark.enrollment_id),
                    "target_enrollment_id": str(self.targets[index].pk),
                    "source_legacy_point_id": 901 + index,
                    "target_legacy_point_id": 911 + index,
                    "target_counter_before": 2,
                    "target_counter_after": 0,
                    "source_mark_pin": {field: pins[field] for field in fields},
                }
            )
        for key, value in {"ORG": str(self.org.pk), "PERIOD": str(self.source.period_id)}.items():
            mocked = patch.object(spec, key, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.bind_authority()

    def mapping(self, entity, legacy, label, target):
        record = LegacyEntityMap.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=legacy,
            source_row_hash="b" * 64,
            transform_version="fixture",
            target_model_label=label,
            target_pk=str(target),
            created_run=self.run_record,
            state="migrated",
        )
        ensure_initial_version(record)

    @staticmethod
    def header(pk, uniqid, group):
        return {
            "id": pk,
            "uniqid": uniqid,
            "lesson_id": 501,
            "teacher_id": 601,
            "groups_id": json.dumps([group]),
            "students_id": json.dumps([801, 802]),
            "semestr": 14,
            "active": 1,
            "fake": 0,
            "sonra_sil": 0,
        }

    @staticmethod
    def point(pk, student, journal, token):
        return {
            "id": pk,
            "student_id": student,
            "journal_uniqid": journal,
            "month_id": "09",
            "day_number": "22",
            "time": "09:00:00",
            "sem_muh": 1,
            "lab": 0,
            "point": token,
            "excusable": 0,
            "update_counter": 0,
            "updated_at": None,
        }

    def bind_authority(self):
        self.authority = json.dumps(self.authority_value, sort_keys=True).encode()
        self.authority_sha = hashlib.sha256(self.authority).hexdigest()
        if hasattr(self, "authority_patch"):
            self.authority_patch.stop()
        self.authority_patch = patch.object(spec, "CONFLICT_AUTHORITY_SHA", self.authority_sha, create=True)
        self.authority_patch.start()
        self.addCleanup(self.authority_patch.stop)

    def manifest(self):
        return {
            "format": "reaudit-journal-structure/1",
            "organization_id": str(self.org.pk),
            "period_id": str(self.source.period_id),
            "operation": "owner_present_conflict",
            "target_ids": [str(mark.pk) for mark in self.marks],
            "authority_sha256": self.authority_sha,
        }

    def execute(self, **kwargs):
        return op.run(
            organization=self.org,
            actor=self.actor,
            manifest=self.manifest(),
            authority_bytes=self.authority,
            **kwargs,
        )

    def apply(self):
        dry = self.execute()
        return self.execute(apply=True, expected_baseline=dry["baseline"])

    def test_dry_run_has_no_writes_then_exact_apply_repeat_and_formal_undo(self):
        zero_before = list(LessonMark.objects.filter(pk=self.zero.pk).values())
        all_before = {row["id"]: row for row in LessonMark.objects.order_by("pk").values()}
        authority_before = copy.deepcopy(self.authority_value)
        with CaptureQueriesContext(connection) as captured:
            dry = self.execute()
        writes = [q["sql"] for q in captured if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])
        self.assertEqual(dry["planned"], 2)
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["changed"], 2)
        self.assertEqual(JournalCorrection.objects.count(), 2)
        changed_ids = {mark.pk for mark in self.marks}
        for after in LessonMark.objects.order_by("pk").values():
            before = all_before[after["id"]]
            difference = {field for field in before if before[field] != after[field]}
            self.assertEqual(difference & {"status"}, {"status"} if after["id"] in changed_ids else set())
            self.assertLessEqual(difference, {"status", "updated_at"} if after["id"] in changed_ids else set())
        self.assertEqual(self.authority_value, authority_before)
        self.assertEqual(LessonMark.objects.filter(pk__in=[m.pk for m in self.marks], status="present").count(), 2)
        for mark in self.marks:
            mark.refresh_from_db()
            self.assertEqual(mark.entered_by_id, self.teacher.pk)
            self.assertIsNone(mark.score)
        self.assertEqual(list(LessonMark.objects.filter(pk=self.zero.pk).values()), zero_before)
        self.assertEqual(
            list(
                Enrollment.objects.filter(pk__in=[e.pk for e in self.targets]).values_list("absence_hours", flat=True)
            ),
            [0, 0],
        )
        self.assertEqual(self.execute()["status"], "already_applied")
        self.assertEqual(JournalCorrection.objects.count(), 2)
        receipts = apps.get_model("audit.AuditLog").objects.filter(resource_type=spec.RESOURCE)
        self.assertEqual(receipts.filter(new_values__operation="apply").count(), 1)
        undo = self.execute(undo=result["receipt"])
        self.execute(apply=True, undo=result["receipt"], expected_baseline=undo["baseline"])
        self.assertEqual(LessonMark.objects.filter(pk__in=[m.pk for m in self.marks], status="absent").count(), 2)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")
        self.assertEqual(JournalCorrection.objects.count(), 2)
        self.assertEqual(receipts.filter(new_values__operation="undo").count(), 1)
        self.assertEqual(list(LessonMark.objects.filter(pk=self.zero.pk).values()), zero_before)

    def test_source_numeric_zero_and_any_score_are_refused_without_mutation(self):
        for score in (0, 7):
            with self.subTest(score=score), transaction.atomic():
                LessonMark.objects.filter(pk=self.marks[0].pk).update(score=score)
                # Even a newly reviewed pin cannot authorize attendance changes to a graded cell.
                stored = rows(LessonMark.objects.filter(pk=self.marks[0].pk))[0]
                pin = self.authority_value["cases"][0]["source_mark_pin"]
                self.authority_value["cases"][0]["source_mark_pin"] = {field: stored[field] for field in pin}
                self.bind_authority()
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertEqual(JournalCorrection.objects.count(), 0)
                transaction.set_rollback(True)

    def test_changed_source_status_and_reactivated_source_are_refused(self):
        with transaction.atomic():
            LessonMark.objects.filter(pk=self.marks[0].pk).update(status="present")
            with self.assertRaises(ValueError):
                self.execute()
            transaction.set_rollback(True)
        CourseOffering.objects.filter(pk=self.source.pk).update(is_active=True)
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(JournalCorrection.objects.exists())

    def test_existing_target_numeric_zero_is_preserved_and_refuses_correction(self):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.target,
            date=self.lesson.date,
            start_time=self.lesson.start_time,
            end_time=self.lesson.end_time,
            kind=self.lesson.kind,
            hours=2,
        )
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.targets[0],
            status="present",
            score=0,
            entered_by=self.other,
        )
        before = list(LessonMark.objects.filter(pk=mark.pk).values())
        with self.assertRaises(ValueError), transaction.atomic():
            self.execute()
        self.assertEqual(list(LessonMark.objects.filter(pk=mark.pk).values()), before)
        self.assertFalse(JournalCorrection.objects.exists())

    def test_source_authority_numeric_target_and_blank_never_become_present_authority(self):
        original = copy.deepcopy(self.authority_value)
        for token in ("0", "8", "", "qb"):
            with self.subTest(token=token):
                self.authority_value = copy.deepcopy(original)
                self.authority_value["source"]["points"][1]["point"] = token
                self.bind_authority()
                with self.assertRaises(ValueError):
                    self.execute()
        self.assertFalse(JournalCorrection.objects.exists())

    def test_credit_change_invalidates_dry_baseline_and_preserves_credit_rows(self):
        dry = self.execute()
        credit = apps.get_model("registrar.AbsenceCredit").objects.create(
            organization=self.org,
            enrollment=self.source_enrollments[0],
            hours=1,
            actor=self.actor,
            request_token=uuid4(),
            reason="Synthetic reviewed credit",
            old_absence_hours=2,
            new_absence_hours=1,
        )
        type(credit).objects.create(
            organization=self.org,
            enrollment=self.targets[0],
            hours=1,
            actor=self.actor,
            request_token=uuid4(),
            reason="Synthetic successor credit",
            old_absence_hours=1,
            new_absence_hours=0,
        )
        before = list(type(credit).objects.order_by("pk").values())
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.apply()
        self.assertEqual(list(type(credit).objects.order_by("pk").values()), before)
        self.assertEqual(
            list(
                Enrollment.objects.filter(pk__in=[e.pk for e in self.targets]).values_list("absence_hours", flat=True)
            ),
            [0, 0],
        )

    def test_foreign_actor_profile_refuses(self):
        self.actor.profile.organization = fixtures.make_org("conflict-foreign")
        self.actor.profile.save(update_fields=["organization"])
        with self.assertRaisesRegex(ValueError, "actor_profile"), transaction.atomic():
            self.execute()
        self.assertFalse(JournalCorrection.objects.exists())

    def test_extra_unreviewed_target_is_refused(self):
        manifest = self.manifest()
        manifest["target_ids"].append(str(self.zero.pk))
        with self.assertRaises(ValueError), transaction.atomic():
            op.run(
                organization=self.org,
                actor=self.actor,
                manifest=manifest,
                authority_bytes=self.authority,
            )
        self.assertFalse(JournalCorrection.objects.exists())

    def test_human_edit_after_apply_refuses_undo_without_overwriting_zero(self):
        result = self.apply()
        LessonMark.objects.filter(pk=self.zero.pk).update(score=1)
        with self.assertRaisesRegex(ValueError, "post_apply_graph_changed"), transaction.atomic():
            self.execute(undo=result["receipt"])
        self.zero.refresh_from_db()
        self.assertEqual(self.zero.score, 1)
        self.assertFalse(apps.get_model("registrar.CorrectionReversal").objects.exists())

    def test_changed_source_timestamp_pin_requires_new_review(self):
        LessonMark.objects.filter(pk=self.marks[0].pk).update(
            updated_at=self.marks[0].updated_at + dt.timedelta(seconds=1)
        )
        with self.assertRaisesRegex(ValueError, "mark_changed"), transaction.atomic():
            self.execute()
        self.assertFalse(JournalCorrection.objects.exists())

    def test_wrong_individual_counter_forecast_requires_review(self):
        self.authority_value["cases"][0]["target_counter_after"] = 1
        self.bind_authority()
        with self.assertRaises(ValueError), transaction.atomic():
            self.execute()
        self.assertFalse(JournalCorrection.objects.exists())

    def test_status_postcondition_failure_rolls_back_formal_corrections(self):
        from apps.registrar import reaudit_attendance_conflict as conflict

        dry = self.execute()
        original = conflict.apply

        def wrong_final_status(*args, **kwargs):
            corrections = original(*args, **kwargs)
            with journal_unlock():
                LessonMark.objects.filter(pk=self.marks[0].pk).update(status="absent")
            return corrections

        with (
            patch.object(conflict, "apply", side_effect=wrong_final_status),
            self.assertRaisesRegex(ValueError, "conflict_postcondition"),
        ):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(LessonMark.objects.filter(pk__in=[m.pk for m in self.marks], status="absent").count(), 2)
        self.assertFalse(JournalCorrection.objects.exists())

    def test_post_write_graph_guard_rolls_back_both_corrections(self):
        dry = self.execute()
        original = state.protected
        calls = []

        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            calls.append(True)
            if len(calls) == 2:
                value["unexpected_mutation"] = True
            return value

        with (
            patch.object(state, "protected", side_effect=changed),
            self.assertRaisesRegex(ValueError, "protected_graph"),
        ):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(LessonMark.objects.filter(pk__in=[m.pk for m in self.marks], status="absent").count(), 2)
        self.assertFalse(JournalCorrection.objects.exists())
