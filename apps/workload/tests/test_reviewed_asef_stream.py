"""Real PG: shared60h contact without multiplying load or touching academic history."""

import copy
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.registrar.public import teacher_journal_list

from ..models import TeacherAssignment
from ..services import reviewed_asef_stream_repair as repair
from ..services import reviewed_asef_stream_spec as spec
from ..services import reviewed_asef_stream_state as state
from ..services import reviewed_two_catalog_schema as schema
from ..services.reviewed_leyla_catalog_graph import RepairError, bounded, digest
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class ReviewedAsefStreamTests(TestCase):
    def setUp(self):
        self.org = make_org("asef-stream")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="ASEF")
        self.teacher = get_user_model().objects.create_user(
            "asef-stream-teacher", first_name="Asəf", last_name="Qəribov"
        )
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        self.teacher.profile.organization, self.teacher.profile.patronymic = self.org, "Heydər"
        self.teacher.profile.save(update_fields=["organization", "patronymic"])
        self.task = make_task(self.org, self.stack["chair"], status="amended")
        self.keeper = make_row(self.task, self.stack, lecture_total=23, seminar_total=22)
        Group = apps.get_model("organizations.OrgUnit")
        self.parent = Group.objects.create(
            organization=self.org, parent=self.stack["specialty"], unit_type="group", name="536 BI", slug="asef-bi"
        )
        self.children = [
            Group.objects.create(
                organization=self.org,
                parent=self.stack["specialty"],
                unit_type="group",
                name="536 BI" + str(n),
                slug="asef-bi" + str(n),
                settings={"parent_group": str(self.parent.pk)},
            )
            for n in (1, 2)
        ]
        self.duplicate = make_row(
            self.task, {**self.stack, "group": self.children[1]}, lecture_total=8, seminar_total=7
        )
        for row in (self.keeper, self.duplicate):
            type(row).objects.filter(pk=row.pk).update(credits="4", credits_value=4)
            row.refresh_from_db()
        for row, amounts in ((self.keeper, (23, 22)), (self.duplicate, (8, 7))):
            for kind, hours in zip(("lecture", "seminar"), amounts):
                TeacherAssignment.objects.create(
                    organization=self.org,
                    row=row,
                    teacher=self.teacher,
                    activity=kind,
                    hours=hours,
                    note="Original allocation retained for exact undo",
                )
        self.courses, self.versions = [], []
        for index, (group, hours, plan) in enumerate(
            zip(
                [self.stack["group"], *self.children],
                [45, 30, 15],
                [{"lecture": 23, "seminar": 22}, {}, {"lecture": 8, "seminar": 7}],
            )
        ):
            course = apps.get_model("registrar.CourseOffering").objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                group=group,
                period=self.stack["period"],
                instructor=self.teacher,
                lesson_hours=hours,
            )
            self.courses.append(course)
            student = get_user_model().objects.create_user("asef-student" + str(index))
            activate_member(self.org, student, "student", permissions=["course.view"])
            enrollment = apps.get_model("registrar.Enrollment").objects.create(
                organization=self.org, offering=course, student=student
            )
            lesson = apps.get_model("registrar.Lesson").objects.create(
                organization=self.org,
                offering=course,
                date=timezone.localdate(),
                hours=2,
                kind="lecture" if index == 0 else "seminar",
                instructor=self.teacher if index == 0 else None,
            )
            apps.get_model("registrar.LessonMark").objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=enrollment,
                status=["present", "absent", "excused"][index],
                score=0 if index == 0 else None,
            )
            syllabus = apps.get_model("syllabus.Syllabus").objects.create(
                organization=self.org,
                subject=course.subject,
                offering=course,
                period=course.period,
                author=self.teacher,
            )
            version = apps.get_model("syllabus.SyllabusVersion").objects.create(
                organization=self.org,
                syllabus=syllabus,
                applies_to_period=course.period,
                status="approved",
                plan_hours=plan,
                approved_by=self.actor,
                approved_at=timezone.now(),
                locked_at=timezone.now(),
            )
            apps.get_model("syllabus.SyllabusSection").objects.create(
                organization=self.org,
                version=version,
                section_id="week",
                data={"rows": [{"topic": "Original correct own60h source", "lecture": 30, "seminar": 30}]},
            )
            type(syllabus).objects.filter(pk=syllabus.pk).update(current_version=version, approved_version=version)
            self.versions.append(version)
        rows = {
            r["id"]: r for r in bounded(type(self.keeper).objects.filter(pk__in=[self.keeper.pk, self.duplicate.pk]))
        }
        keep, dup = str(self.keeper.pk), str(self.duplicate.pk)
        groups = [self.stack["group"], *self.children]
        pin = copy.deepcopy(spec.PINS)
        pin.update(
            organization_id=str(self.org.pk),
            period_id=str(self.stack["period"].pk),
            teacher=self.teacher.pk,
            subject=str(self.stack["subject"].pk),
            task=str(self.task.pk),
            chair=str(self.task.chair_id),
            keeper=keep,
            duplicate=dup,
            bi_parent=str(self.parent.pk),
            teacher_fall_hours=60,
            bridge=[],
        )
        pin["row_before"], pin["row_after"] = rows, {
            keep: {
                "lecture_plan": 30,
                "lecture_total": 30,
                "seminar_plan": 30,
                "seminar_total": 30,
                "union_count": 2,
                "subgroup_count": 1,
                "total_hours": 60,
                "specialty_id": None,
                "groups_text": "Shared groups",
            },
            dup: {"lecture_plan": 0, "lecture_total": 0, "seminar_plan": 0, "seminar_total": 0, "total_hours": 0},
        }
        pin["row_groups_before"] = {keep: [str(groups[0].pk)], dup: [str(groups[2].pk)]}
        pin["row_groups_after"] = {keep: sorted(str(g.pk) for g in groups), dup: [str(groups[2].pk)]}
        pin["groups"] = {
            r["id"]: r for r in bounded(Group.objects.filter(pk__in=[g.pk for g in [*groups, self.parent]]))
        }
        pin["assignments"] = {
            r["id"]: {key: r[key] for key in ("id", "row_id", "teacher_id", "hours", "activity", "is_hourly_paid")}
            for r in bounded(TeacherAssignment.objects.filter(row__in=[self.keeper, self.duplicate]))
        }
        pin["courses"] = {
            r["id"]: r for r in bounded(type(self.courses[0]).objects.filter(pk__in=[c.pk for c in self.courses]))
        }
        pin["counts"] = {str(c.pk): {"lessons": 1, "marks": 1, "enrollments": 1} for c in self.courses}
        pin["syllabi"] = {
            r["id"]: r for r in bounded(apps.get_model("syllabus.Syllabus").objects.filter(offering__in=self.courses))
        }
        pin["version_before"] = {
            r["id"]: r for r in bounded(type(self.versions[0]).objects.filter(pk__in=[v.pk for v in self.versions]))
        }
        pin["body_sha256"] = {
            str(v.pk): digest(list(v.sections.order_by("section_id").values("section_id", "data")))
            for v in self.versions
        }
        pin["task_pin"] = bounded(type(self.task).objects.filter(pk=self.task.pk))[0]
        pin["subject_pin"] = bounded(type(self.stack["subject"]).objects.filter(pk=self.stack["subject"].pk))[0]
        for key, value in {
            "PINS": pin,
            "ORG": str(self.org.pk),
            "PERIOD": str(self.stack["period"].pk),
            "TEACHER": self.teacher.pk,
            "KEEPER": keep,
            "DUPLICATE": dup,
            "SCHEMA": schema.fingerprints(),
        }.items():
            p = patch.object(spec, key, value)
            p.start()
            self.addCleanup(p.stop)

    def execute(self, **options):
        return repair.run(organization=self.org, actor=self.actor, **options)

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def test_apply_repeat_and_exact_undo_preserve_all_cells_credit_and_original_metadata(self):
        before = state.snapshot(self.org)
        old_marks = list(apps.get_model("registrar.LessonMark").objects.values())
        result = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(state.protected(before), state.protected(after))
        self.assertEqual(list(apps.get_model("registrar.LessonMark").objects.values()), old_marks)
        self.assertEqual(TeacherAssignment.objects.filter(row__in=[self.keeper, self.duplicate]).count(), 2)
        self.assertEqual(
            sum(TeacherAssignment.objects.filter(teacher=self.teacher).values_list("hours", flat=True)), 60
        )
        self.assertEqual(
            set(
                type(self.courses[0])
                .objects.filter(pk__in=[c.pk for c in self.courses])
                .values_list("lesson_hours", flat=True)
            ),
            {60},
        )
        self.assertEqual(type(self.keeper).objects.get(pk=self.keeper.pk).credits_value, 4)
        self.assertEqual(self.execute()["status"], "already_applied")
        for version in self.versions:
            version.refresh_from_db()
            self.assertEqual(version.plan_hours, spec.PLAN)
            self.assertEqual(version.status, "approved")
        self.assertEqual(self.keeper.groups.count(), 3)
        dry = self.execute(undo=result["receipt"])
        self.execute(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")

    def test_all_three_actual_journals_become_current_with_both_kinds(self):
        self.apply()
        q = teacher_journal_list.own_visible_queryset(type(self.courses[0]).objects.all(), self.teacher, self.org)
        self.assertEqual(set(q.values_list("pk", flat=True)), {c.pk for c in self.courses})
        for kind in ("lecture", "seminar"):
            self.assertEqual(
                set(teacher_journal_list.filter_kind(q, kind).values_list("pk", flat=True)),
                {c.pk for c in self.courses},
            )

    def test_new_human_score_after_dry_blocks_apply(self):
        baseline = self.execute()["baseline"]
        apps.get_model("registrar.LessonMark").objects.filter(score=0).update(score=9)
        with self.assertRaisesRegex(RepairError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=baseline)
        self.assertEqual(self.duplicate.assignments.count(), 2)

    def test_new_human_score_after_apply_blocks_undo(self):
        result = self.apply()
        apps.get_model("registrar.LessonMark").objects.filter(score=0).update(score=9)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"), transaction.atomic():
            self.execute(undo=result["receipt"])

    def test_changed_source_body_and_other_teacher_assignment_hold(self):
        section = self.versions[0].sections.first()
        section.data = {"rows": [{"topic": "New human content"}]}
        section.save(update_fields=["data"])
        with self.assertRaisesRegex(RepairError, "source_body"), transaction.atomic():
            self.execute()

    def test_other_teacher_and_changed_credit_hold(self):
        TeacherAssignment.objects.filter(row=self.duplicate, activity="lecture").update(teacher=self.actor)
        with self.assertRaisesRegex(RepairError, "assignment_identity"), transaction.atomic():
            self.execute()

    def test_extra_rival_row_is_not_silently_absorbed(self):
        make_row(self.task, self.stack, lecture_total=0, seminar_total=0)
        with self.assertRaisesRegex(RepairError, "other_official_row"), transaction.atomic():
            self.execute()

    def test_late_failure_rolls_back_rows_groups_contact_caps_and_assignments(self):
        before = state.snapshot(self.org)
        with (
            patch.object(repair, "write_version_plan_hours", return_value=False),
            self.assertRaises(RepairError),
            transaction.atomic(),
        ):
            self.apply()
        self.assertEqual(state.snapshot(self.org), before)

    def test_unreviewed_schema_and_inactive_teacher_are_refused(self):
        with (
            patch.object(schema, "fingerprints", return_value={}),
            self.assertRaisesRegex(RepairError, "schema"),
            transaction.atomic(),
        ):
            self.execute()
        self.teacher.is_active = False
        self.teacher.save(update_fields=["is_active"])
        with self.assertRaisesRegex(RepairError, "identity"), transaction.atomic():
            self.execute()
