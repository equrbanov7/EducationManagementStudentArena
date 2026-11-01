"""One absent source lesson: fixed28 PRESENT, all historical QB/scores unchanged."""

import copy
import datetime
import hashlib
import io
import json
import re
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services import reviewed_content as service
from apps.legacy_import.services import reviewed_content_28_spec as fixed
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.reviewed_content_28_undo import undo
from apps.legacy_import.services.reviewed_content_contract import ContentError, validate_payload
from apps.legacy_import.services.reviewed_content_spec import ORG
from apps.legacy_import.services.reviewed_content_state import digest
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import source28_spec as allocation
from apps.workload.services.scoped_snapshot.four_cell_history import collect_available_history
from apps.workload.services.scoped_snapshot.history_scope import CompiledHistoryScope
from core.rls import apply_rls_request_context, reset_rls_context


class Source28Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("source28_operator")
        cls.org = Organization.objects.create(id=ORG, slug="qku", name="QKU", org_type="university", owner=cls.actor)
        cls.actor.profile.organization = cls.org
        cls.actor.profile.save(update_fields=["organization"])
        cls.chair = OrgUnit.objects.create(
            id=allocation.WORKLOAD_CHAIR,
            organization=cls.org,
            name="Chair",
            slug="source28-chair",
            unit_type="department",
        )
        cls.group = OrgUnit.objects.create(
            id=fixed.SPEC["group_id"],
            organization=cls.org,
            name="235 M",
            slug="source28-group",
            unit_type="group",
            parent=cls.chair,
        )
        cls.period = AcademicPeriod.objects.create(
            id=fixed.SPEC["period_id"],
            organization=cls.org,
            name="Fall",
            academic_year="2026/2027",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.teacher = User.objects.create_user(
            id=fixed.SPEC["teacher_id"], username="source28_teacher", first_name="Ad", last_name="Soyad"
        )
        cls.teacher.profile.organization, cls.teacher.profile.patronymic = cls.org, "Ata"
        cls.teacher.profile.save(update_fields=["organization", "patronymic"])
        Membership.objects.create(
            organization=cls.org,
            user=cls.teacher,
            role=cls.org.roles.get(name="teacher"),
            scope_unit=cls.chair,
            is_primary=True,
        )
        cls.subject = Subject.objects.create(
            id=fixed.SPEC["subject_id"], organization=cls.org, code="SRC28", name="Subject"
        )
        cls.offering = CourseOffering.objects.create(
            id=fixed.TARGET,
            organization=cls.org,
            subject=cls.subject,
            period=cls.period,
            group=cls.group,
            instructor=cls.teacher,
            lesson_hours=60,
        )
        cls.task = TeachingTask.objects.create(
            id=allocation.WORKLOAD_TASK,
            organization=cls.org,
            chair=cls.chair,
            academic_year="2026/2027",
            status="amended",
        )
        cls.row = TeachingTaskRow.objects.create(
            id=allocation.WORKLOAD_ROW,
            organization=cls.org,
            task=cls.task,
            subject=cls.subject,
            period=cls.period,
            lecture_plan=30,
            lecture_total=30,
            seminar_plan=30,
            seminar_total=30,
            total_hours=60,
        )
        cls.row.groups.add(cls.group)
        TeacherAssignment.objects.create(
            id=allocation.WORKLOAD_ASSIGNMENT,
            organization=cls.org,
            row=cls.row,
            teacher=cls.teacher,
            activity="seminar",
            hours=30,
            is_hourly_paid=True,
        )
        cls.program = Program.objects.create(organization=cls.org, code="SRC28", name="Program")
        cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
        run = create_run(
            organization=cls.org,
            actor=cls.actor,
            authorize=lambda **kw: True,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=31,
            schema_version="test",
            transform_version="test",
            mode="rehearsal",
        )
        cls.source_run = start_run(run_id=run.pk, actor=cls.actor, authorize=lambda **kw: True)
        cls.raw = {
            "format": "reviewed-journal-content/1",
            "organization_id": ORG,
            "academic_year": "2026/2027",
            "semester": {"id": 14, "name": "2026/2027 Payız", "type": "autumn"},
            "until": "2026-11-01",
            "targets": [fixed.TARGET],
            "journals": [
                {
                    "id": fixed.SPEC["journal_id"],
                    "uniqid": fixed.SPEC["journal_uniqid"],
                    "lesson_id": fixed.SPEC["legacy_subject_id"],
                    "semestr": 14,
                    "teacher_id": fixed.SPEC["legacy_teacher_id"],
                    "groups_id": [fixed.SPEC["legacy_group_id"]],
                    "fake": 0,
                    "sonra_sil": 0,
                    "active": 1,
                }
            ],
            "points": [],
            "dates": [
                {
                    "id": fixed.CALENDAR_IDS[0],
                    "journal_id": fixed.SPEC["journal_id"],
                    "month": 10,
                    "day": 29,
                    "time": "15:15",
                }
            ],
            "workers": [
                {"id": fixed.SPEC["legacy_teacher_id"], "first_name": "Ad", "last_name": "Soyad", "father_name": "Ata"}
            ],
            "students": [],
            "excuse_windows": [],
        }
        for entity, sid, label, target in [
            ("worker", fixed.SPEC["legacy_teacher_id"], "auth.user", cls.teacher.pk),
            ("lesson_subject", fixed.SPEC["legacy_subject_id"], "registrar.subject", cls.subject.pk),
            ("group_unit", fixed.SPEC["legacy_group_id"], "organizations.orgunit", cls.group.pk),
        ]:
            cls.mapping(entity, sid, label, target)
        for point, c in fixed.CASES.items():
            user = User.objects.create_user(id=c["student_id"], username="source28_student" + str(point))
            user.profile.organization = cls.org
            user.profile.save(update_fields=["organization"])
            Membership.objects.create(
                organization=cls.org,
                user=user,
                role=cls.org.roles.get(name="student"),
                scope_unit=cls.group,
                is_primary=True,
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=cls.curriculum,
                admission_year=2024,
                group=cls.group,
            )
            Enrollment.objects.create(id=c["enrollment_id"], organization=cls.org, student=user, offering=cls.offering)
            cls.mapping("student", c["source_student_id"], "auth.user", user.pk)
            cls.raw["students"].append({"id": c["source_student_id"], "group_id": fixed.SPEC["legacy_group_id"]})
            cls.raw["points"].append(
                {
                    "id": point,
                    "journal_uniqid": fixed.SPEC["journal_uniqid"],
                    "month_id": "10",
                    "day_number": "29",
                    "student_id": c["source_student_id"],
                    "point": "ie",
                    "time": fixed.START,
                    "lab": 0,
                    "sem_muh": 0,
                    "excusable": 0,
                    "update_counter": 0,
                    "updated_at": "",
                }
            )

    @classmethod
    def mapping(cls, entity, source, label, target):
        return LegacyEntityMap.objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=str(source),
            target_model_label=label,
            target_pk=str(target),
            state="migrated",
            source_row_hash="b" * 64,
            transform_version="test",
            created_run=cls.source_run,
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.actor.pk, org_id=ORG, bypass=False)
        self.addCleanup(reset_rls_context)
        self.raw = copy.deepcopy(self.raw)
        self.pin = patch.object(fixed, "PAYLOAD_DIGEST", digest(self.raw))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.clock = patch.object(service.timezone, "localdate", return_value=datetime.date(2026, 11, 1))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def execute(self, **kwargs):
        sha = kwargs.pop("source_sha256", fixed.SOURCE_SHA)
        return service.execute(
            data=validate_payload(self.raw, target_ids=[fixed.TARGET]),
            source_sha256=sha,
            user=self.actor,
            organization=self.org,
            **kwargs,
        )

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def test_create_exact_present_lesson_topic_null_authors_repeat_and_undo(self):
        dry = self.execute()
        self.assertEqual((dry["missing_lessons"], dry["missing_marks"]), (1, 28))
        self.assertFalse(Lesson.objects.exists())
        done = self.execute(apply=True, expected_baseline=dry["baseline"])
        lesson = Lesson.objects.get(pk=fixed.LESSON)
        self.assertEqual(
            (lesson.kind, lesson.hours, lesson.topic, lesson.instructor_id, lesson.created_by_id, lesson.end_time),
            ("seminar", 2, fixed.TOPIC, None, None, None),
        )
        self.assertFalse(lesson.is_legacy_synthesised)
        self.assertEqual(LessonMark.objects.filter(status="present", score=None, entered_by=None).count(), 28)
        self.assertEqual(self.apply()["already_done"], 1)
        args = dict(
            data=validate_payload(self.raw, target_ids=[fixed.TARGET]),
            source_sha256=fixed.SOURCE_SHA,
            user=self.actor,
            organization=self.org,
            batch=done["batch"],
        )
        review = undo(**args)
        undone = undo(**args, apply=True, expected_baseline=review["baseline"])
        self.assertEqual((undone["deleted_lessons"], undone["deleted_marks"]), (1, 28))
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(LessonMark.objects.exists())
        self.assertEqual(undo(**args)["already_undone"], 1)
        with self.assertRaises(ContentError):
            self.apply()

    def test_source_tampering_future_extra_qb_or_points_rejected(self):
        for field, value in [("point", "qb"), ("point", "0"), ("month_id", "11"), ("sem_muh", 3)]:
            raw = copy.deepcopy(self.raw)
            raw["points"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ContentError):
                service.execute(
                    data=validate_payload(raw, target_ids=[fixed.TARGET]),
                    source_sha256=fixed.SOURCE_SHA,
                    user=self.actor,
                    organization=self.org,
                )
        with self.assertRaises(ContentError):
            self.execute(source_sha256="0" * 64)

    def test_old_deleted_lesson_different_uuid_detected_even_no_current_lesson(self):
        old_lesson = str(uuid.uuid4())
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=fixed.TARGET,
            changes=[
                {
                    "student": "—",
                    "item": fixed.DATE + " · " + str(Lesson(kind="seminar").get_kind_display()),
                    "old": "dərs sütunu",
                    "new": "silindi",
                }
            ],
            old_values={"lesson_id": old_lesson},
        )
        with self.assertRaisesMessage(ContentError, "contrary_history"):
            self.apply()
        self.assertFalse(LessonMark.objects.exists())

    def test_clear_and_unresolved_course_audit_both_hold(self):
        c = next(iter(fixed.CASES.values()))
        user = get_user_model().objects.get(pk=c["student_id"])
        with transaction.atomic():
            AuditLog.objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="registrar.grade.mark",
                resource_id=fixed.TARGET,
                changes=[
                    {
                        "student": user.username,
                        "item": fixed.DATE + " · " + str(Lesson(kind="seminar").get_kind_display()),
                        "old": "9",
                        "new": "—",
                    }
                ],
            )
            with self.assertRaisesMessage(ContentError, "contrary_history"):
                self.execute()
            transaction.set_rollback(True)
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.mark",
            resource_id=fixed.TARGET,
            changes=[{"unrecognized": "intent"}],
        )
        with self.assertRaisesMessage(ContentError, "unresolved_course_audit"):
            self.execute()

    def test_any_canonical_dropped_course_mark_blocks_not_copied(self):
        c = next(iter(fixed.CASES.values()))
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=OrgUnit.objects.create(
                organization=self.org, name="Other group", slug="source28-other-group", unit_type="group"
            ),
            instructor=self.teacher,
            is_active=False,
        )
        enr = Enrollment.objects.create(
            organization=self.org, offering=other, student_id=c["student_id"], status="dropped"
        )
        lesson = Lesson.objects.create(
            organization=self.org, offering=other, date=fixed.DATE, start_time="08:30", kind="lecture", hours=2
        )
        mark = LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enr, status="absent", score=0)
        with self.assertRaisesMessage(ContentError, "existing_content_without_original"):
            self.apply()
        mark.refresh_from_db()
        self.assertEqual((mark.status, mark.score), ("absent", 0))
        self.assertEqual(LessonMark.objects.count(), 1)

    def test_inactive_deleted_blocked_profiles_and_allocation_drift_hold(self):
        c = next(iter(fixed.CASES.values()))
        profile = get_user_model().objects.get(pk=c["student_id"]).profile
        for field, value in [("is_deleted", True), ("deleted_at", timezone.now()), ("blocked_at", timezone.now())]:
            original = getattr(profile, field)
            setattr(profile, field, value)
            profile.save(update_fields=[field])
            with self.subTest(field=field), self.assertRaisesMessage(ContentError, "active_tenant_profiles"):
                self.execute()
            setattr(profile, field, original)
            profile.save(update_fields=[field])
        TeacherAssignment.objects.filter(pk=allocation.WORKLOAD_ASSIGNMENT).update(hours=29)
        with self.assertRaisesMessage(ContentError, "fresh_history_or_allocation"):
            self.execute()

    def test_baseline_drift_write_failure_atomicity_and_counter_no_extra_qb(self):
        dry = self.execute()
        self.row.groups_text = "changed"
        self.row.save(update_fields=["groups_text"])
        with self.assertRaises(ContentError):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.row.refresh_from_db()
        c = next(iter(fixed.CASES.values()))
        Enrollment.objects.filter(pk=c["enrollment_id"]).update(absence_hours=2)
        with self.assertRaisesMessage(ContentError, "must_not_change_existing_qb_counter"):
            self.apply()
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(LessonMark.objects.exists())

    def test_history_scope_accepts_only_exact_compiled_object(self):
        scope = allocation.history_scope()
        fake = CompiledHistoryScope(scope.prefix, scope.undo_operation, scope.cases_json, scope.source_keys_json)
        with self.assertRaisesMessage(ValueError, "compiled_history_scope_required"):
            collect_available_history(_scope=fake)
        with self.assertRaisesMessage(ValueError, "compiled_history_scope_required"):
            collect_available_history(_scope={})

    def test_unlocatable_deleted_old_lesson_and_foreign_tenant_isolation(self):
        other = Organization.objects.create(
            slug="source28-foreign", name="Other", org_type="university", owner=self.actor
        )
        AuditLog.objects.create(
            organization=other,
            user=self.actor,
            action="delete",
            resource_type="registrar.Lesson",
            resource_id=str(uuid.uuid4()),
        )
        self.assertEqual(self.execute()["missing_marks"], 28)
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="delete",
            resource_type="registrar.Lesson",
            resource_id=str(uuid.uuid4()),
        )
        with self.assertRaisesMessage(ContentError, "unlocatable_lesson_deletion"):
            self.execute()

    def test_correct_existing_qb_zero_preserved_and_view_not_edit(self):
        c = next(iter(fixed.CASES.values()))
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date="2026-10-01",
            start_time="08:30",
            kind="seminar",
            hours=2,
        )
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment_id=c["enrollment_id"],
            status="absent",
            score=0,
            entered_by=self.teacher,
        )
        Enrollment.objects.filter(pk=c["enrollment_id"]).update(absence_hours=2)
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="view",
            resource_type="registrar.grade.mark",
            resource_id=fixed.TARGET,
        )
        self.apply()
        mark.refresh_from_db()
        self.assertEqual((mark.status, mark.score, mark.entered_by_id), ("absent", 0, self.teacher.pk))
        self.assertEqual(Enrollment.objects.get(pk=c["enrollment_id"]).absence_hours, 2)

    def test_injected_write_failure_rolls_back_whole_new_lesson_and_marks(self):
        dry = self.execute()
        original = service._write

        def fail_after_write(decision):
            original(decision)
            raise ContentError("injected_write_failure")

        with (
            patch.object(service, "_write", side_effect=fail_after_write),
            self.assertRaisesMessage(ContentError, "injected_write_failure"),
        ):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(LessonMark.objects.exists())

    def test_foreign_superadmin_cannot_undo_or_observe_already_undone_receipt(self):
        done = self.apply()
        other_user = get_user_model().objects.create_superuser("source28_outside")
        other_org = Organization.objects.create(
            slug="source28-outside", name="Outside", org_type="university", owner=other_user
        )
        other_user.profile.organization = other_org
        other_user.profile.save(update_fields=["organization"])
        args = dict(
            data=validate_payload(self.raw, target_ids=[fixed.TARGET]),
            source_sha256=fixed.SOURCE_SHA,
            user=self.actor,
            organization=self.org,
            batch=done["batch"],
        )
        with self.assertRaisesMessage(ContentError, "tenant_actor_required"):
            undo(**{**args, "user": other_user})
        dry = undo(**args)
        undo(**args, apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesMessage(ContentError, "tenant_actor_required"):
            undo(**{**args, "user": other_user})

    def test_undo_cli_safe_summary_and_parser_errors_do_not_echo_private_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_text(json.dumps(self.raw))
            path.chmod(0o600)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(fixed, "SOURCE_SHA", sha):
                done = self.apply()
                output = io.StringIO()
                args = [
                    "--actor",
                    self.actor.username,
                    "--manifest",
                    str(path),
                    "--manifest-sha256",
                    sha,
                    "--batch",
                    done["batch"],
                ]
                call_command("undo_reviewed_source28_content", *args, stdout=output)
                text = output.getvalue()
                self.assertRegex(
                    text,
                    r"^reviewed_source28_undo: mode=dry_run baseline=[a-f0-9]{64} deleted_lessons=1 deleted_marks=28 already_undone=0\n$",
                )
                self.assertNotIn(str(path), text)
                baseline = re.search(r"baseline=([a-f0-9]{64})", text).group(1)
                call_command(
                    "undo_reviewed_source28_content",
                    *args,
                    "--apply",
                    "--expected-baseline",
                    baseline,
                    stdout=io.StringIO(),
                )
                with patch(
                    "apps.legacy_import.management.commands.undo_reviewed_source28_content.load_payload",
                    side_effect=OSError("PRIVATE_PATH_NOT_FOR_OUTPUT"),
                ):
                    with self.assertRaisesMessage(CommandError, "source28_undo_input_or_database_guard_failed"):
                        call_command("undo_reviewed_source28_content", *args, stdout=io.StringIO())

    def test_no_roster_or_blank_source_fill_for_extra_enrolled_student(self):
        user = get_user_model().objects.create_user("source28_no_source_point")
        user.profile.organization = self.org
        user.profile.save(update_fields=["organization"])
        Membership.objects.create(
            organization=self.org,
            user=user,
            role=self.org.roles.get(name="student"),
            scope_unit=self.group,
            is_primary=True,
        )
        extra = Enrollment.objects.create(organization=self.org, student=user, offering=self.offering)
        self.apply()
        self.assertEqual(LessonMark.objects.count(), 28)
        self.assertFalse(LessonMark.objects.filter(enrollment=extra).exists())

    def test_unknown_contenterror_lowercase_token_never_printed_by_fixed_cli(self):
        options = ["--actor", self.actor.username, "--manifest", "unused.json", "--manifest-sha256", "0" * 64]
        commands = [
            ("undo_reviewed_source28_content", ["--batch", "unused"], "source28_undo_guard_failed"),
            ("repair_reviewed_journal_content", ["--targets", fixed.TARGET], "reviewed_source28_guard_failed"),
        ]
        for name, args, safe in commands:
            error = io.StringIO()
            with (
                self.subTest(command=name),
                patch(
                    "apps.legacy_import.management.commands." + name + ".load_payload",
                    side_effect=ContentError("personname123"),
                ),
            ):
                with self.assertRaisesMessage(CommandError, safe) as result:
                    call_command(name, *options, *args, stderr=error, stdout=io.StringIO())
                self.assertNotIn("personname123", str(result.exception) + error.getvalue())
