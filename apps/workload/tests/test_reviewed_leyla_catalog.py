"""Real migrated PG: two load rows, three complete classes and 550 preserved cells."""

import copy
import datetime as dt
from contextlib import ExitStack
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar import teacher_journal_list
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonMark,
    ScheduleSlot,
    Subject,
)
from apps.syllabus.public import content_fingerprints, import_migrated_version
from apps.workload.models import TeacherAssignment, TeachingTask, WorkloadAmendment
from apps.workload.services import reviewed_leyla_catalog_repair as repair
from apps.workload.services import reviewed_leyla_catalog_spec as spec
from apps.workload.services import reviewed_leyla_catalog_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded, digest, normal
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class ReviewedLeylaCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("leyla-catalog")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save()
        cls.teacher = User.objects.create_user("catalog-teacher")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        Profile = apps.get_model("accounts.UserProfile")
        Profile.objects.filter(user_id__in=[cls.actor.pk, cls.teacher.pk]).update(
            organization=cls.org, access_state="active", is_deleted=False, deleted_at=None, blocked_at=None
        )
        cls.stacks = [make_structure(cls.org, code="LC" + str(i)) for i in range(3)]
        cls.period = cls.stacks[0]["period"]
        cls.task = make_task(cls.org, cls.stacks[0]["chair"])
        named = [
            Subject.objects.create(organization=cls.org, code="named-" + str(i), name="Named " + str(i))
            for i in range(2)
        ]
        cls.rows = [make_row(cls.task, cls.stacks[0]), make_row(cls.task, cls.stacks[1], seminar_total=30)]
        for index, row in enumerate(cls.rows):
            row.subject = named[index]
            row.period = cls.period
            row.save()
        cls.rows[1].groups.set([cls.stacks[1]["group"], cls.stacks[2]["group"]])
        # The two-group row refers to one canonical source subject, not two new catalogs.
        cls.old_subjects = [cls.stacks[0]["subject"], cls.stacks[1]["subject"], cls.stacks[1]["subject"]]
        cls.assignments = []
        for index, row in enumerate(cls.rows):
            for kind, hours in (("lecture", 30), ("seminar", 15 if index == 0 else 30)):
                cls.assignments.append(
                    TeacherAssignment.objects.create(
                        organization=cls.org,
                        row=row,
                        teacher=cls.teacher,
                        activity=kind,
                        hours=hours,
                        groups_note="",
                        note="Preserve original allocation note",
                    )
                )
        cls.filled, cls.empty, cls.enrs, cls.syllabi = [], [], [], []
        for index, (roster_count, cell_count, slots) in enumerate(((28, 246, 9), (13, 141, 12), (15, 163, 12))):
            group = cls.stacks[index]["group"]
            group.settings = {"sector": "az", "degree_level": "bachelor", "unrelated": {"keep": index}}
            group.save()
            row = cls.rows[0 if index == 0 else 1]
            common = dict(
                organization=cls.org,
                period=cls.period,
                group=group,
                instructor=cls.teacher,
                lesson_hours=45 if index == 0 else 60,
            )
            a = CourseOffering.objects.create(subject=row.subject, **common)
            b = CourseOffering.objects.create(subject=cls.old_subjects[index], **common)
            cls.empty.append(a)
            cls.filled.append(b)
            for kind, hour in (("lecture", 10), ("seminar", 12)):
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=a,
                    weekday=1 if index == 0 else (2 if kind == "lecture" or index == 1 else 3),
                    start_time=f"{hour}:00",
                    end_time=f"{hour + 1}:30",
                    kind=kind,
                    room="Room1",
                )
            for offering in (a, b):
                AssessmentScheme.objects.create(organization=cls.org, offering=offering)
            enrs = []
            for number in range(roster_count):
                student = User.objects.create_user(f"catalog-student-{index}-{number}")
                activate_member(cls.org, student, "student", permissions=["course.view", "grade.view"])
                Enrollment.objects.create(organization=cls.org, offering=a, student=student)
                enrs.append(Enrollment.objects.create(organization=cls.org, offering=b, student=student))
            cls.enrs.extend(enrs)
            lessons = [
                Lesson.objects.create(
                    organization=cls.org,
                    offering=b,
                    date=dt.date(2026, 9, 16) + dt.timedelta(days=n),
                    start_time="15:15",
                    kind="lecture" if n % 2 else "seminar",
                    hours=2,
                    topic=f"Actual source class {n}",
                )
                for n in range(slots)
            ]
            marks = []
            for n in range(cell_count):
                mark = LessonMark(
                    organization=cls.org,
                    lesson=lessons[n // roster_count],
                    enrollment=enrs[n % roster_count],
                    status="present",
                    score=None,
                )
                if n == 0:
                    mark.score = Decimal("0")
                elif n == 1:
                    mark.status = "absent"
                elif n == 2:
                    mark.status = "excused"
                elif n == 3:
                    mark.score, mark.entered_by = Decimal("8"), cls.teacher
                marks.append(mark)
            LessonMark.objects.bulk_create(marks)
            Enrollment.objects.filter(pk=enrs[1].pk).update(absence_hours=2)
            component = AssessmentComponent.objects.create(
                organization=cls.org, offering=b, name="Written exam", max_score=10
            )
            ComponentScore.objects.create(
                organization=cls.org,
                component=component,
                enrollment=enrs[0],
                score=7,
                exam_source={"attempt_id": "retained-current-exam"},
            )
            syl, version = import_migrated_version(
                organization=cls.org,
                subject=b.subject,
                period=cls.period,
                offering=b,
                author=cls.teacher,
                chair_unit=cls.stacks[0]["chair"],
                approved_at=timezone.now(),
                plan_hours={"lecture": 30, "seminar": 15 if index == 0 else 30, "lab": 0},
                section_data={
                    "info": {"language": "az"},
                    "desc": {"description": "Own approved historical body"},
                    "week": {"rows": [{"topic": "Real course", "lecture": 30, "seminar": 15 if index == 0 else 30}]},
                },
            )
            cls.syllabi.append((syl, version))
        TeachingTask.objects.filter(pk=cls.task.pk).update(status="distributed")
        cls.task.refresh_from_db()
        run = apps.get_model("legacy_import.LegacyMigrationRun").objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="fixture_v1",
            transform_version="fixture_v1",
            mode="rehearsal",
        )
        run.status = "running"
        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at"])
        identities = [
            ("worker", "863", "auth.user", cls.teacher.pk),
            ("worker_materialisation", "863", "auth.user", cls.teacher.pk),
        ]
        identities += [
            ("group_unit", str(600 + i), "organizations.orgunit", stack["group"].pk)
            for i, stack in enumerate(cls.stacks)
        ]
        identities += [
            ("lesson_subject", str(2500 + i), "registrar.subject", subject.pk)
            for i, subject in enumerate(cls.old_subjects[:2])
        ]
        cls.bridge = []
        for entity, legacy, label, target in identities:
            obj = apps.get_model("legacy_import.LegacyEntityMap").objects.create(
                organization=cls.org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=legacy,
                target_pk=str(target),
                target_model_label=label,
                state="migrated",
                source_row_hash="b" * 64,
                transform_version="fixture_v1",
                created_run=run,
            )
            cls.bridge.append(
                {
                    k: getattr(obj, k)
                    for k in ("entity_type", "legacy_pk", "target_pk", "target_model_label", "state", "source_row_hash")
                }
            )

    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        offerings = self.empty + self.filled
        fields = ("id", "group_id", "period_id", "subject_id", "instructor_id", "lesson_hours", "is_active")
        rowpins = {}
        for index, row in enumerate(self.rows):
            raw = normal(type(row).objects.filter(pk=row.pk).values().get())
            fields_row = {
                k: v
                for k, v in raw.items()
                if k not in ("id", "subject_id", "created_at", "updated_at", "sort_order", "organization_id")
            }
            rowpins[str(row.pk)] = {
                "before_subject": str(row.subject_id),
                "after_subject": str(self.old_subjects[index].pk),
                "fields": fields_row,
                "groups": sorted(str(g) for g in row.groups.values_list("pk", flat=True)),
            }
        assignments = normal(
            list(
                TeacherAssignment.objects.filter(row__in=self.rows)
                .order_by("pk")
                .values("id", "row_id", "teacher_id", "activity", "hours")
            )
        )
        marks = bounded(LessonMark.objects.filter(lesson__offering__in=self.filled))
        values = {
            "ORG": str(self.org.pk),
            "CHAIR": str(self.task.chair_id),
            "TEACHER": self.teacher.pk,
            "TASK": str(self.task.pk),
            "PERIOD": str(self.period.pk),
            "ROWS": rowpins,
            "ASSIGNMENTS": assignments,
            "OFFERINGS": {str(o.pk): normal({k: getattr(o, k) for k in fields}) for o in offerings},
            "EMPTY": [str(o.pk) for o in self.empty],
            "FILLED": [str(o.pk) for o in self.filled],
            "GROUPS": {
                str(s["group"].pk): normal(
                    {k: getattr(s["group"], k) for k in ("name", "parent_id", "unit_type", "settings", "is_active")}
                )
                for s in self.stacks
            },
            "SUBJECTS": {str(o.subject_id): {"code": o.subject.code, "name": o.subject.name} for o in offerings},
            "BRIDGE": self.bridge,
            "MARK_COUNT": 550,
            "PAIRS": {str(a.pk): str(b.pk) for a, b in zip(self.empty, self.filled)},
            "MARK_SHA256": digest([{k: m[k] for k in spec.MARK_FIELDS} for m in marks]),
            "ROSTERS": {
                str(o.group_id): {
                    "count": len(
                        users := sorted(Enrollment.objects.filter(offering=o).values_list("student_id", flat=True))
                    ),
                    "sha256": digest(users),
                }
                for o in self.filled
            },
            "SYLLABI": [
                {
                    "offering_id": str(o.pk),
                    "syllabus_id": str(s.pk),
                    "version_id": str(v.pk),
                    "canonical_body_sha256": content_fingerprints({r.section_id: r.data for r in v.sections.all()})[
                        "canonical_body_sha256"
                    ],
                }
                for o, (s, v) in zip(self.filled, self.syllabi)
            ],
        }
        for name, value in values.items():
            self.patches.enter_context(patch.object(spec, name, copy.deepcopy(value)))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(
            apply=True, expected_baseline=dry["baseline"], expected_schedule_sha=dry["schedule_source_sha256"]
        )

    def test_dry_apply_repeat_undo_preserve_550_cells_schemes_exams_and_approved_body(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        self.assertEqual((dry["rows"], dry["applied"]), (2, False))
        applied = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(repair._protected(before), repair._protected(after))
        self.assertTrue(after["corrected"])
        self.assertEqual(LessonMark.objects.count(), 550)
        self.assertEqual(ComponentScore.objects.count(), 3)
        self.assertEqual(WorkloadAmendment.objects.count(), 2)
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.assertEqual(AuditLog.objects.filter(resource_type=repair.RESOURCE).count(), 1)
        undo = self.run_repair(undo=applied["receipt"])
        result = self.run_repair(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(result["status"], "undone")
        self.assertEqual(repair._protected(before), repair._protected(state.snapshot(self.org)))
        self.assertFalse(state.snapshot(self.org)["corrected"])
        self.assertEqual(WorkloadAmendment.objects.count(), 4)
        self.assertEqual(self.run_repair(apply=True)["status"], "already_undone")
        self.assertEqual(self.run_repair(undo=applied["receipt"], apply=True)["status"], "already_undone")

    def test_current_teacher_discovers_populated_classes_after_relink_without_new_permissions(self):
        qs = CourseOffering.objects.filter(organization=self.org, instructor=self.teacher)
        before = set(
            teacher_journal_list.project(qs, self.teacher, self.org)
            .filter(journal_is_current_load=True)
            .values_list("pk", flat=True)
        )
        self.assertEqual(before, {o.pk for o in self.empty})
        self.apply()
        after = set(
            teacher_journal_list.project(qs, self.teacher, self.org)
            .filter(journal_is_current_load=True)
            .values_list("pk", flat=True)
        )
        self.assertEqual(after, {o.pk for o in self.filled})

    def test_stale_baseline_rejected_before_any_row_change(self):
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline="0" * 64)
        self.assertFalse(state.snapshot(self.org)["corrected"])
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_foreign_superadmin_denied_before_receipt_access_and_after_undo(self):
        outsider = User.objects.create_superuser("catalog-foreign", password="x")
        with self.assertRaisesRegex(RepairError, "actor_tenant"):
            repair.run(organization=self.org, actor=outsider, undo="bad")
        result = self.apply()
        for receipt in (result["receipt"], "unknown"):
            with self.assertRaisesRegex(RepairError, "actor_tenant"):
                repair.run(organization=self.org, actor=outsider, undo=receipt)

    def test_named_human_syllabus_is_not_automatically_approved_or_replaced(self):
        syl, _ = import_migrated_version(
            organization=self.org,
            subject=self.empty[0].subject,
            offering=self.empty[0],
            period=self.period,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Preserve new Named content"}},
        )
        draft = apps.get_model("syllabus.SyllabusVersion").objects.create(
            organization=self.org, syllabus=syl, major=1, minor=1, status="draft", created_by=self.teacher
        )
        section = apps.get_model("syllabus.SyllabusSection").objects.create(
            organization=self.org, version=draft, section_id="desc", data={"description": "Human draft; keep unchanged"}
        )
        type(syl).objects.filter(pk=syl.pk).update(current_version=draft)
        with self.assertRaisesRegex(RepairError, "named_syllabus"):
            self.run_repair()
        self.assertTrue(type(syl).objects.filter(pk=syl.pk).exists())
        draft.refresh_from_db()
        section.refresh_from_db()
        self.assertEqual(draft.status, "draft")
        self.assertEqual(section.data, {"description": "Human draft; keep unchanged"})

    def test_current_named_grade_or_lesson_holds(self):
        Lesson.objects.create(organization=self.org, offering=self.empty[0], date="2026-10-30", kind="lecture", hours=2)
        with self.assertRaisesRegex(RepairError, "no_longer_empty"):
            self.run_repair()

    def test_assignment_owner_hours_or_groups_changed_hold(self):
        TeacherAssignment.objects.filter(pk=self.assignments[0].pk).update(hours=29)
        with self.assertRaisesRegex(RepairError, "allocations"):
            self.run_repair()

    def test_protected_exam_edit_after_apply_blocks_undo(self):
        result = self.apply()
        ComponentScore.objects.filter(pk=ComponentScore.objects.first().pk).update(score=9)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_zero_excused_authors_and_absence_cache_are_never_rewritten(self):
        marks = list(LessonMark.objects.order_by("pk").values())
        enrs = list(Enrollment.objects.order_by("pk").values())
        self.apply()
        self.assertEqual(marks, list(LessonMark.objects.order_by("pk").values()))
        self.assertEqual(enrs, list(Enrollment.objects.order_by("pk").values()))
        self.assertTrue(LessonMark.objects.filter(score=0).exists())
        self.assertTrue(LessonMark.objects.filter(status="excused").exists())

    def test_failure_in_second_row_rolls_back_first_row_amendments_and_audit(self):
        original = state.snapshot
        count = 0

        def fail(org):
            nonlocal count
            count += 1
            if count == 3:
                raise RepairError("deliberate")
            return original(org)

        with patch.object(state, "snapshot", side_effect=fail), self.assertRaises(RepairError):
            self.apply()
        self.assertFalse(state.snapshot(self.org)["corrected"])
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_actor_contradictory_deleted_or_blocked_profile_denied(self):
        Profile = apps.get_model("accounts.UserProfile")
        Profile.objects.filter(user=self.actor).update(blocked_at=timezone.now())
        with self.assertRaisesRegex(RepairError, "profile_inactive"):
            self.run_repair()

    def test_command_is_atomic_even_when_transaction_scoped_rls_disabled(self):
        output = StringIO()
        call_command("repair_reviewed_leyla_catalog", actor=self.actor.username, stdout=output)
        self.assertRegex(
            output.getvalue(),
            r"^reviewed_leyla_catalog: status=dry_run rows=2 schedule=[0-9a-f]{64} slots=6 applied=0 baseline=[0-9a-f]{64} receipt=none\n$",
        )
        self.assertTrue(connection.in_atomic_block)

    def test_actual_six_original_slots_parked_canonical_copies_keep_every_time_and_kind(self):
        old = {str(s["id"]): normal(s) for s in ScheduleSlot.all_objects.order_by("pk").values()}
        dry = self.run_repair()
        self.assertEqual(dry["schedule_slots"], 6)
        result = self.apply()
        current = list(ScheduleSlot.all_objects.order_by("pk").values())
        self.assertEqual(len(current), 12)
        self.assertEqual(ScheduleSlot.objects.filter(is_parked=False, offering__in=self.filled).count(), 6)
        self.assertEqual(ScheduleSlot.objects.filter(is_parked=True, offering__in=self.empty).count(), 6)
        saved = AuditLog.objects.get(resource_id=result["receipt"], resource_type=repair.RESOURCE)
        for pair in saved.new_values["schedule_pairs"]:
            source = ScheduleSlot.all_objects.get(pk=pair["source"])
            target = ScheduleSlot.all_objects.get(pk=pair["target"])
            self.assertEqual(str(source.pk), old[str(source.pk)]["id"])
            for field in ("weekday", "start_time", "end_time", "room", "week_type", "kind"):
                self.assertEqual(getattr(source, field), getattr(target, field))
            self.assertEqual(source.created_by_id, None)
            self.assertEqual(target.created_by_id, self.actor.pk)

    def test_source_schedule_separate_fresh_review_required(self):
        dry = self.run_repair()
        with self.assertRaisesRegex(RepairError, "fresh_schedule_review"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"], expected_schedule_sha="0" * 64)
        self.assertFalse(ScheduleSlot.objects.filter(is_parked=True).exists())

    def test_foreign_or_different_current_timetable_holds(self):
        source = ScheduleSlot.objects.filter(offering=self.empty[0]).first()
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.filled[0],
            weekday=source.weekday,
            start_time="18:00",
            end_time="19:30",
            kind=source.kind,
        )
        with self.assertRaisesRegex(RepairError, "canonical_schedule_already_present"):
            self.run_repair()

    def test_undo_after_canonical_schedule_edit_holds_all_originals_parked(self):
        result = self.apply()
        ScheduleSlot.objects.filter(offering=self.filled[0], is_parked=False).update(room="Changed later")
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])
        self.assertEqual(ScheduleSlot.objects.filter(offering__in=self.empty, is_parked=True).count(), 6)

    def test_named_exam_zero_is_real_current_content_and_blocks_relink(self):
        component = AssessmentComponent.objects.create(organization=self.org, offering=self.empty[0], name="New exam")
        ComponentScore.objects.create(
            organization=self.org,
            component=component,
            enrollment=Enrollment.objects.filter(offering=self.empty[0]).first(),
            score=0,
        )
        with self.assertRaisesRegex(RepairError, "named_enrollment_content"):
            self.run_repair()

    def test_new_canonical_teacher_workload_authority_is_not_overwritten(self):
        row = make_row(self.task, self.stacks[0])
        row.subject = self.old_subjects[0]
        row.save()
        with self.assertRaisesRegex(RepairError, "existing_canonical_workload_authority"):
            self.run_repair()
        type(row).objects.filter(pk=row.pk).update(total_hours=0, lecture_total=0, seminar_total=0, lecture_plan=45)
        with self.assertRaisesRegex(RepairError, "canonical_plan_hours_conflict"):
            self.run_repair()

    def test_unknown_mark_changes_and_timestamp_precision_are_protected(self):
        mark = LessonMark.objects.first()
        LessonMark.objects.filter(pk=mark.pk).update(score=3)
        with self.assertRaisesRegex(RepairError, "canonical_cells_changed"):
            self.run_repair()

    def test_deleted_teacher_flag_cannot_be_overridden_by_active_access_state(self):
        apps.get_model("accounts.UserProfile").objects.filter(user=self.teacher).update(is_deleted=True)
        with self.assertRaisesRegex(RepairError, "teacher_profile_inactive"):
            self.run_repair()

    def test_unrelated_later_timetable_conflict_blocks_undo_atomically(self):
        result = self.apply()
        source = ScheduleSlot.all_objects.filter(offering=self.empty[0], kind="lecture").get()
        other_subject = Subject.objects.create(organization=self.org, code="other-conflict", name="Later authority")
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=other_subject,
            period=self.period,
            group=self.empty[0].group,
            instructor=self.teacher,
        )
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=other,
            weekday=source.weekday,
            start_time=source.start_time,
            end_time=source.end_time,
            room=source.room,
        )
        with self.assertRaisesRegex(RepairError, "undo_schedule_conflict"):
            dry = self.run_repair(undo=result["receipt"])
            self.run_repair(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(state.snapshot(self.org)["corrected"])
        self.assertEqual(ScheduleSlot.objects.filter(offering__in=self.empty, is_parked=True).count(), 6)

    def test_non_superadmin_and_other_organization_cannot_apply(self):
        with self.assertRaisesRegex(RepairError, "tenant_superadmin"):
            repair.run(organization=self.org, actor=self.teacher, apply=True)
        other = make_org("leyla-foreign-org")
        with self.assertRaisesRegex(RepairError, "tenant_superadmin"):
            repair.run(organization=other, actor=self.actor)

    def test_partial_joint_time_overlap_is_held_during_dry_not_after_writes(self):
        ScheduleSlot.objects.filter(offering=self.empty[2], kind="lecture").update(start_time="10:15", end_time="11:45")
        with self.assertRaisesRegex(RepairError, "proposed_schedule_overlap"):
            self.run_repair()
        self.assertFalse(WorkloadAmendment.objects.exists())
        self.assertEqual(ScheduleSlot.objects.filter(is_parked=True).count(), 0)


class LeylaCommandOuterTransactionTests(TransactionTestCase):
    def test_real_command_sets_tenant_inside_atomic_for_both_rls_settings(self):
        from django.test import override_settings

        from core.rls import reset_rls_context

        for scoped in (False, True):
            with self.subTest(scoped=scoped), override_settings(RLS_TRANSACTION_SCOPED=scoped):
                org = make_org("leyla-wrapper-" + str(scoped))
                actor = org.owner
                actor.is_superuser = True
                actor.save()
                self.assertFalse(connection.in_atomic_block)

                def checked(*, checked_org=org, **kwargs):
                    self.assertTrue(connection.in_atomic_block)
                    with connection.cursor() as c:
                        c.execute("SELECT current_setting('app.current_org_id',true)")
                        self.assertEqual(c.fetchone()[0], str(checked_org.pk))
                    return {"status": "dry_run", "rows": 2, "applied": False, "baseline": "0" * 64, "receipt": None}

                with patch.object(spec, "ORG", str(org.pk)), patch.object(repair, "run", side_effect=checked):
                    reset_rls_context(local=False)
                    call_command("repair_reviewed_leyla_catalog", actor=actor.username, stdout=StringIO())
                self.assertFalse(connection.in_atomic_block)
                with connection.cursor() as c:
                    c.execute("SELECT current_setting('app.current_org_id',true)")
                    self.assertNotEqual(c.fetchone()[0], str(org.pk))

    def test_command_never_prints_unreviewed_exception_args(self):
        from django.core.management.base import CommandError

        org = make_org("leyla-private-error")
        actor = org.owner
        actor.is_superuser = True
        actor.save()
        for failure in (RepairError({"private": "fixture-content"}), RepairError("unreviewed_private_value")):
            with patch.object(spec, "ORG", str(org.pk)), patch.object(repair, "run", side_effect=failure):
                with self.assertRaisesMessage(CommandError, "leyla_reviewed_guard_failed") as caught:
                    call_command("repair_reviewed_leyla_catalog", actor=actor.username, stdout=StringIO())
                self.assertNotIn("fixture-content", str(caught.exception))
                self.assertNotIn("unreviewed_private_value", str(caught.exception))
