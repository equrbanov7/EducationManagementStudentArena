"""Müəllim təyinatı açılışa DƏRHAL düşür + provenans (sahib 2026-09-25).

Yoxlanılır: ``assign_teacher`` jurnal sahibini ``confirm_distribution``-u gözləmədən
yazır; yükün öz yazdığı müəllim dəyişəndə əvəzlənir; «Fənn təhvili» və cədvəl
redaktorunun qoyduğu FƏRQLİ müəllim əzilmir; vakant → boş; bal yaza bilməyən müəllim
→ boş + hesabat (çökmə yox); köhnə kafedra qaralaması açılış YARATMIR (yalnız
mövcudu yeniləyir); yeni qrup əlavəsi öz açılışını alır; birləşik qrupa alt qrup
tələbələri düşür; ``teachers_for_offering`` API-si; ``sync_plan_offerings`` əmri.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import schedule_editor
from apps.registrar.models import CourseOffering, Enrollment, TeachingHandover
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeachingTask, TeachingTaskRow
from apps.workload.public import teachers_for_offering
from apps.workload.services import assign_teacher, confirm_distribution, save_row, unassign
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_row, make_task
from .test_plan_offerings import PlanOfferingBase

User = get_user_model()


class _TeacherBase(PlanOfferingBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.teacher_a = cls._teacher("a")
        cls.teacher_b = cls._teacher("b")
        cls.teacher_c = cls._teacher("c")
        cls.weak = User.objects.create_user(f"{cls.code}.weak", f"{cls.code}w@x.test", "pw")
        activate_member(
            cls.org,
            cls.weak,
            "assistant",  # kafedra hovuzundadır, amma `grade.input` YOXDUR
            permissions=["workload.view"],
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.COURSE,
        )

    @classmethod
    def _teacher(cls, suffix):
        user = User.objects.create_user(f"{cls.code}.t.{suffix}", f"{cls.code}t{suffix}@x.test", "pw")
        activate_member(
            cls.org,
            user,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.COURSE,
        )
        return user

    def approved_row(self, **kwargs):
        task, row = self.office_task(**kwargs)
        self.approve(task)
        row = TeachingTaskRow.objects.select_related("task", "task__chair").get(pk=row.pk)
        return task, row

    def assign(self, row, teacher, *, activity=Activity.LECTURE, hours=30, assignment=None):
        return assign_teacher(
            row=row,
            actor=self.actor(self.chair_head),
            activity=activity,
            teacher_id=getattr(teacher, "pk", None),
            hours=hours,
            assignment=assignment,
        )

    def offering(self):
        return CourseOffering.objects.get(organization=self.org, subject=self.stack["subject"])


class ImmediateInstructorTest(_TeacherBase):
    code = "P2I"

    def test_assignment_sets_the_instructor_before_confirmation(self):
        _task, row = self.approved_row()
        self.assertIsNone(self.offering().instructor_id)
        assignment = self.assign(row, self.teacher_a)
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)
        self.assertEqual(assignment.offering_sync["instructor_set"], 1)
        self.assertEqual(TeachingTask.objects.get(pk=row.task_id).status, TaskStatus.DISTRIBUTING)

    def test_changing_the_lecturer_replaces_the_workload_set_instructor(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        changed = self.assign(row, self.teacher_b, assignment=assignment)
        self.assertEqual(self.offering().instructor_id, self.teacher_b.pk)
        self.assertEqual(changed.offering_sync["instructor_replaced"], 1)

    def test_handover_instructor_is_never_overwritten(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        offering = self.offering()
        TeachingHandover.objects.create(
            organization=self.org,
            offering=offering,
            from_instructor=self.teacher_a,
            to_instructor=self.teacher_c,
            from_instructor_name="A",
            to_instructor_name="C",
            reason="Müəllim işdən çıxdı — fənn təhvil verildi",
            performed_by=self.chair_head,
        )
        CourseOffering.objects.filter(pk=offering.pk).update(instructor=self.teacher_c)
        changed = self.assign(row, self.teacher_b, assignment=assignment)
        self.assertEqual(self.offering().instructor_id, self.teacher_c.pk)
        self.assertEqual(changed.offering_sync["preserved_handover"], 1)

    def test_schedule_editor_instructor_is_preserved(self):
        _task, row = self.approved_row()
        schedule_editor.resolve_offering(
            actor=self.chair_head,
            organization=self.org,
            group=self.stack["group"],
            period=self.stack["period"],
            subject=self.stack["subject"],
            instructor=self.teacher_c,
        )
        assignment = self.assign(row, self.teacher_a)
        self.assertEqual(self.offering().instructor_id, self.teacher_c.pk)
        self.assertEqual(assignment.offering_sync["preserved_foreign"], 1)
        self.assign(row, None, activity=Activity.SEMINAR, hours=30)
        result = confirm_distribution(task=TeachingTask.objects.get(pk=row.task_id), actor=self.actor(self.chair_head))
        self.assertEqual(result["sync"]["preserved_foreign"], 1)
        self.assertEqual(self.offering().instructor_id, self.teacher_c.pk)

    def test_vacating_the_lecture_leaves_the_offering_empty(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        vacant = self.assign(row, None, assignment=assignment)
        self.assertIsNone(self.offering().instructor_id)
        self.assertEqual(vacant.offering_sync["instructor_cleared"], 1)

    def test_unassigning_the_lecturer_clears_the_instructor(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        report = unassign(assignment=assignment, actor=self.actor(self.chair_head))
        self.assertIsNone(self.offering().instructor_id)
        self.assertEqual(report["instructor_cleared"], 1)

    def test_teacher_without_grade_input_is_reported_not_crashed(self):
        _task, row = self.approved_row()
        weak = self.assign(row, self.weak)
        self.assertIsNone(self.offering().instructor_id)
        self.assertEqual(weak.offering_sync["instructor_blocked"], 1)
        strong = self.assign(row, self.teacher_a, assignment=weak)
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)
        back = self.assign(row, self.weak, assignment=strong)
        self.assertIsNone(self.offering().instructor_id)  # əvvəlki sahib çıxdı, yenisi yaza bilmir
        self.assertEqual((back.offering_sync["instructor_cleared"], back.offering_sync["instructor_blocked"]), (1, 1))

    def test_every_instructor_write_on_an_existing_offering_is_audited(self):
        from apps.audit.models import AuditLog

        _task, row = self.approved_row()
        self.assign(row, self.teacher_a)
        entry = AuditLog.objects.get(reason="workload.offering_instructor_synced")
        self.assertEqual(entry.new_values["instructor"], str(self.teacher_a.pk))
        self.assertEqual(entry.new_values["outcome"], "set")


class LegacyDraftAndRowEditTest(_TeacherBase):
    code = "P2L"

    def test_legacy_chair_draft_creates_offerings_only_at_confirmation(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.chair_head)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        row = TeachingTaskRow.objects.select_related("task").get(pk=row.pk)
        assignment = self.assign(row, self.teacher_a)
        self.assertFalse(CourseOffering.objects.filter(organization=self.org).exists())
        self.assertEqual(assignment.offering_sync["not_created"], 1)
        task.refresh_from_db()
        result = confirm_distribution(task=task, actor=self.actor(self.chair_head))
        self.assertEqual(result["sync"]["created"], 1)
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)
        self.assertTrue(Enrollment.objects.filter(offering=self.offering(), student=self.student).exists())

    def test_legacy_draft_still_updates_an_existing_offering(self):
        CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=self.stack["group"]
        )
        task = make_task(self.org, self.stack["chair"], created_by=self.chair_head)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        self.assign(TeachingTaskRow.objects.select_related("task").get(pk=row.pk), self.teacher_a)
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)
        self.assertTrue(Enrollment.objects.filter(offering=self.offering(), student=self.student).exists())

    def test_amendment_changes_the_journal_owner_at_once(self):
        from apps.workload.constants import AmendmentReason, AmendmentTarget
        from apps.workload.services import open_amendment

        task = make_task(self.org, self.stack["chair"], created_by=self.chair_head)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        row = TeachingTaskRow.objects.select_related("task").get(pk=row.pk)
        assignment = self.assign(row, self.teacher_a)
        task.refresh_from_db()
        confirm_distribution(task=task, actor=self.actor(self.chair_head))
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)
        task.refresh_from_db()
        open_amendment(
            task=task,
            actor=self.actor(self.chair_head),
            target_kind=AmendmentTarget.ASSIGNMENT,
            target_id=assignment.pk,
            reason=AmendmentReason.STAFF_CHANGE,
            note="Müəllim dəyişdi — kadr əmri №12",
        )
        row = TeachingTaskRow.objects.select_related("task").get(pk=row.pk)
        changed = self.assign(row, self.teacher_b, assignment=assignment)
        self.assertEqual(self.offering().instructor_id, self.teacher_b.pk)  # yenidən təsdiqi GÖZLƏMİR
        self.assertEqual(changed.offering_sync["instructor_replaced"], 1)

    def test_adding_a_group_to_a_distributing_row_opens_its_offering(self):
        _task, row = self.approved_row()
        self.assign(row, self.teacher_a)
        extra = OrgUnit.objects.create(
            organization=self.org,
            name="P2L-236 ing",
            slug="p2l-extra",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        task = TeachingTask.objects.get(pk=row.task_id)
        save_row(
            task=task,
            actor=self.actor(self.chair_head),
            data={"group_ids": [str(self.stack["group"].pk), str(extra.pk)]},
            row=TeachingTaskRow.objects.get(pk=row.pk),
        )
        added = CourseOffering.objects.get(organization=self.org, group=extra)
        self.assertEqual(added.instructor_id, self.teacher_a.pk)


class TeachersForOfferingTest(_TeacherBase):
    code = "P2T"

    def test_split_teaching_is_exposed_for_the_timetable(self):
        _task, row = self.approved_row(lecture_total=30, seminar_total=30, lab_total=20)
        TeachingTaskRow.objects.filter(pk=row.pk).update(lab_plan=20)
        self.assign(row, self.teacher_a)
        self.assign(row, self.teacher_b, activity=Activity.SEMINAR, hours=15)
        self.assign(row, self.teacher_c, activity=Activity.SEMINAR, hours=15)
        info = teachers_for_offering(self.offering())
        self.assertEqual(info["lecture"], self.teacher_a)
        self.assertEqual(info["seminar"], [self.teacher_b, self.teacher_c])
        self.assertEqual(info["lab"], [])
        self.assertEqual(info["hours"], {"lecture": 30, "seminar": 30, "lab": 20})
        self.assertEqual(info["vacant"], ["lab"])
        self.assertEqual(info["row_ids"], [str(row.pk)])

    def test_offering_without_workload_rows_reports_only_its_instructor(self):
        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher_c,
        )
        info = teachers_for_offering(offering)
        self.assertEqual((info["lecture"], info["seminar"], info["row_ids"]), (self.teacher_c, [], []))


class CombinedGroupTest(_TeacherBase):
    code = "P2C"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        def group(name, slug):
            return OrgUnit.objects.create(
                organization=cls.org, name=name, slug=slug, unit_type=OrgUnitType.GROUP, parent=cls.stack["specialty"]
            )

        cls.combined = group("234 K az", "p2c-234k")
        cls.sub_students = [cls._student("s1", group=group("234 K-1", "p2c-234k1"))]
        cls.sub_students.append(cls._student("s2", group=group("234 K-2", "p2c-234k2")))

    def _combined_task(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, {**self.stack, "group": self.combined})
        return task

    def test_subgroup_students_join_the_combined_offering_as_guests(self):
        result = self.approve(self._combined_task())
        offering = CourseOffering.objects.get(organization=self.org, group=self.combined)
        guests = Enrollment.objects.filter(offering=offering)
        self.assertEqual({e.student_id for e in guests}, {s.pk for s in self.sub_students})
        self.assertTrue(all(e.source_group_id for e in guests))  # provenans: alt qrup
        self.assertEqual(result["offerings"]["guest_added"], 2)

    def test_rollup_waits_for_the_current_period(self):
        AcademicPeriod.objects.filter(pk=self.stack["period"].pk).update(is_current=False)
        result = self.approve(self._combined_task())
        offering = CourseOffering.objects.get(organization=self.org, group=self.combined)
        self.assertFalse(Enrollment.objects.filter(offering=offering).exists())
        self.assertEqual(result["offerings"]["guest_deferred"], 2)


class BackfillCommandTest(_TeacherBase):
    code = "P2B"

    def _run(self, *extra):
        out = StringIO()
        call_command("sync_plan_offerings", "--org", self.org.slug, "--year", "2026/2027", *extra, stdout=out)
        return out.getvalue()

    def _approved_without_period(self):
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.office)
        task.submitted_at = timezone.now()
        task.save(update_fields=["submitted_at"])
        return make_row(task, self.stack, with_period=False)

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        row = self._approved_without_period()
        out = self._run()
        self.assertIn("DRY-RUN", out)
        self.assertIn("created=1", out)
        row.refresh_from_db()
        self.assertIsNone(row.period_id)
        self.assertFalse(CourseOffering.objects.filter(organization=self.org).exists())

        self._run("--apply")
        row.refresh_from_db()
        self.assertEqual(row.period_id, self.stack["period"].pk)
        self.assertTrue(Enrollment.objects.filter(offering=self.offering(), student=self.student).exists())
        again = self._run("--apply")
        self.assertNotIn("created=", again)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org).count(), 1)

    def test_legacy_drafts_need_the_explicit_flag(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.chair_head)
        row = make_row(task, self.stack, with_period=False)
        self._run("--apply")
        row.refresh_from_db()
        self.assertEqual(row.period_id, self.stack["period"].pk)  # semestr yenə bağlanır
        self.assertFalse(CourseOffering.objects.filter(organization=self.org).exists())
        self._run("--apply", "--include-drafts")
        self.assertTrue(CourseOffering.objects.filter(organization=self.org).exists())
