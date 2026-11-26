"""MR-000836: ``merge_334f_journals_20261126`` — 334F1 + 334F2 → ana qrup 334F, hər fənn üçün bir jurnal."""

from __future__ import annotations

import datetime
import pathlib
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import services as registrar_services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    SeminarGroup,
    StudentAcademicRecord,
    Subject,
)
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "f334_merge: "
LINE = re.compile(r"^f334_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
User = get_user_model()
T0900, T1010, T1150 = datetime.time(9), datetime.time(10, 10), datetime.time(11, 50)
DAY1, DAY2, DAY3 = datetime.date(2026, 9, 29), datetime.date(2026, 10, 6), datetime.date(2026, 10, 12)


class WiringTest(SimpleTestCase):
    def test_workflow_and_worker_atomic_exemption(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - merge_334f_journals_20261126\n", text)
        self.assertIn("            merge_334f_journals_20261126)\n", text)
        self.assertIn('[ "$COMMAND" = "merge_334f_journals_20261126" ]', text)
        self.assertIn("|f334_merge|", text)
        self.assertIn("^m334f-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)
        exemptions = (ROOT / "scripts" / "check_worker_atomic_coverage.py").read_text(encoding="utf-8")
        self.assertIn('"apps/registrar/management/commands/merge_334f_journals_20261126.py"', exemptions)

    def test_code_slug_is_digit_safe(self):
        from apps.registrar.merge_334f_2026_11_26 import code_slug

        self.assertEqual(code_slug("ÖƏD-5"), "oed-5")
        self.assertEqual(code_slug("Şəhər İqtisadi 2"), "seher_iqtisadi_2")
        self.assertRegex(code_slug("?? ##"), r"^[0-9a-z_-]+$")


class Merge334FTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.admin = User.objects.create_superuser("m334f_admin", "m334f_admin@x.test", "pw")
            cls.org = Organization.objects.create(
                name="M334F Univ",
                slug="m334f-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.admin,
                status="active",
                is_active=True,
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="Filologiya", slug="m334f-fil", unit_type=OrgUnitType.SPECIALTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Dillər", slug="m334f-chair", unit_type=OrgUnitType.CHAIR
            )
            meta = {"course_year": "3", "education_form": "full_time", "language_sector": "az"}
            cls.f1, cls.f2 = (
                OrgUnit.objects.create(
                    organization=cls.org,
                    parent=cls.specialty,
                    name=name,
                    slug=name.lower(),
                    unit_type=OrgUnitType.GROUP,
                    settings=dict(meta),
                )
                for name in ("334F1", "334F2")
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 15),
                end_date=datetime.date(2027, 1, 31),
                is_current=True,
            )
            cls.teacher = cls._user("m334f_t1", "teacher", ["grade.input"])
            cls.teacher2 = cls._user("m334f_t2", "teacher", ["grade.input"])
            program = Program.objects.create(organization=cls.org, code="M334F", name="Filologiya")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            cls.students = {cls.f1.pk: [], cls.f2.pk: []}
            for group, size in ((cls.f1, 3), (cls.f2, 2)):
                for index in range(size):
                    student = cls._user(f"m334f_{group.name.lower()}_{index}", "student", [])
                    StudentAcademicRecord.objects.create(
                        organization=cls.org,
                        student=student,
                        program=program,
                        curriculum=curriculum,
                        group=group,
                        admission_year=2024,
                    )
                    cls.students[group.pk].append(student)
            cls.same = Subject.objects.create(organization=cls.org, code="DÜN-2", name="Dünya ədəbiyyatı-2")
            cls.diff = Subject.objects.create(organization=cls.org, code="ÖƏD-5", name="Öyrənilən əsas dil-5")
            cls.blocked = Subject.objects.create(organization=cls.org, code="SAH", name="Sahibkarlıq")
            cls.offerings = {}
            # Eyni tarix / saat / növ: mühazirə + seminar.
            cls._pair(cls.same, {cls.f1: [(DAY1, LessonKind.LECTURE, T1010), (DAY2, LessonKind.SEMINAR, T1150)]})
            # Bir gündə fərqli saat (29.09): seminarlar alt qruplara bağlanır.
            cls._pair(
                cls.diff,
                {
                    cls.f1: [(DAY1, LessonKind.SEMINAR, T0900), (DAY3, LessonKind.SEMINAR, T1010)],
                    cls.f2: [(DAY1, LessonKind.SEMINAR, T1150), (DAY3, LessonKind.SEMINAR, T1010)],
                },
            )
            # Fərqli müəllim — qoruyucu ailəni bloklayır.
            cls._pair(cls.blocked, {cls.f1: [(DAY2, LessonKind.LECTURE, T0900)]}, second_teacher=cls.teacher2)
            task = TeachingTask.objects.create(
                organization=cls.org, chair=cls.chair, academic_year="2026/2027", status="distributed"
            )
            cls.rows = {}
            for subject in (cls.same, cls.diff, cls.blocked):
                row = TeachingTaskRow.objects.create(
                    organization=cls.org, task=task, subject=subject, period=cls.period, lecture_total=30
                )
                row.groups.set([cls.f1, cls.f2])
                cls.rows[subject.pk] = row
            cls.task = task

    @classmethod
    def _user(cls, username, role_name, permissions):
        user = User.objects.create_user(username, f"{username}@x.test", "pw")
        role, _created = Role.objects.get_or_create(
            organization=cls.org,
            name=role_name,
            defaults={"display_name": role_name.title(), "level": 50, "permissions": list(permissions)},
        )
        Role.objects.filter(pk=role.pk).update(
            is_active=True, permissions=list(permissions), scope_type=RoleScopeType.ORGANIZATION
        )
        Membership.objects.get_or_create(organization=cls.org, user=user, role=role, defaults={"is_active": True})
        return user

    @classmethod
    def _pair(cls, subject, lessons, second_teacher=None):
        """Hər qrupa bir jurnal; ``lessons`` — qrup → [(tarix, növ, saat)] (yoxdursa birincinin dərsləri)."""
        default = next(iter(lessons.values()))
        for group in (cls.f1, cls.f2):
            offering = registrar_services.get_or_create_offering(
                organization=cls.org, subject=subject, period=cls.period, group=group
            )
            offering.instructor = second_teacher if (second_teacher and group == cls.f2) else cls.teacher
            offering.save(update_fields=["instructor"])
            cls.offerings[(subject.pk, group.pk)] = offering
            rows = [
                Enrollment.objects.create(organization=cls.org, student=student, offering=offering)
                for student in cls.students[group.pk]
            ]
            for day, kind, start in lessons.get(group, default):
                lesson = Lesson.objects.create(
                    organization=cls.org, offering=offering, date=day, kind=kind, hours=2, start_time=start
                )
                for row in rows:
                    LessonMark.objects.create(organization=cls.org, lesson=lesson, enrollment=row, status="present")

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _call(self, *extra):
        out = StringIO()
        call_command(
            "merge_334f_journals_20261126", "--org", self.org.slug, "--actor", self.admin.username, *extra, stdout=out
        )
        counts, families, batch = {}, {}, ""
        for line in out.getvalue().splitlines():
            self.assertRegex(line, LINE)
            body = line[len(PREFIX) :]
            if body.startswith("mode="):
                continue
            if body.startswith("batch="):
                batch = body.split("=", 1)[1]
                continue
            pairs = dict(pair.split("=", 1) for pair in body.split())
            if "family" in pairs and "status" in pairs:
                families[pairs["family"]] = pairs
            else:
                counts.update(pairs)
        return counts, families, batch

    def _parent(self):
        return OrgUnit.objects.filter(organization=self.org, name="334F").first()

    def _source(self, subject, group):
        return CourseOffering.objects.get(pk=self.offerings[(subject.pk, group.pk)].pk)

    def _snapshot(self):
        return (
            OrgUnit.objects.filter(organization=self.org).count(),
            CourseOffering.objects.filter(organization=self.org, is_active=True).count(),
            Enrollment.objects.filter(organization=self.org, status="enrolled").count(),
            LessonMark.objects.filter(organization=self.org).count(),
            Lesson.objects.filter(organization=self.org).count(),
            SeminarGroup.objects.filter(organization=self.org).count(),
            sorted(str(unit.settings) for unit in OrgUnit.objects.filter(pk__in=[self.f1.pk, self.f2.pk])),
            sorted(
                (row.pk, tuple(sorted(str(pk) for pk in row.groups.values_list("pk", flat=True))))
                for row in TeachingTaskRow.objects.filter(organization=self.org)
            ),
        )

    def _records(self):
        return sorted(StudentAcademicRecord.objects.filter(organization=self.org).values_list("student_id", "group_id"))

    # ── testlər ───────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        with bypass_rls():
            before = self._snapshot()
        counts, families, batch = self._call()
        self.assertEqual(batch, "")
        self.assertEqual((counts["parent_created"], counts["subgroups_linked"], counts["families"]), ("1", "2", "3"))
        self.assertEqual((counts["subgroup_first_students"], counts["subgroup_second_students"]), ("3", "2"))
        self.assertEqual(counts["families_merged"], "2")
        self.assertEqual(families["dun-2"]["status"], "merged")
        self.assertEqual(families["oed-5"]["status"], "merged")
        self.assertEqual(families["sah"]["status"], "blocked_family_instructors_differ")
        self.assertEqual(families["dun-2"]["first"], str(self.offerings[(self.same.pk, self.f1.pk)].pk)[:8])
        self.assertEqual(families["dun-2"]["second"], str(self.offerings[(self.same.pk, self.f2.pk)].pk)[:8])
        with bypass_rls():
            self.assertEqual(self._snapshot(), before)
            self.assertIsNone(self._parent())

    def test_apply_creates_parent_merges_and_rerun_is_idempotent(self):
        with bypass_rls():
            records = self._records()
        counts, families, batch = self._call("--apply")
        self.assertRegex(batch, r"^m334f-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual((families["dun-2"]["status"], families["oed-5"]["status"]), ("merged", "merged"))
        self.assertEqual(families["sah"]["status"], "blocked_family_instructors_differ")
        with bypass_rls():
            parent = self._parent()
            self.assertTrue(parent.is_active)
            self.assertEqual(parent.parent_id, self.specialty.pk)
            self.assertEqual(parent.settings["created_by_command"], "merge_334f_journals_20261126")
            self.assertEqual(parent.settings["course_year"], "3")
            for unit in OrgUnit.objects.filter(pk__in=[self.f1.pk, self.f2.pk]):
                self.assertEqual(unit.settings["parent_group"], str(parent.pk))
            self.assertEqual(self._records(), records)  # tələbənin rəsmi qrupu dəyişmir

            # Eyni saatlı cüt: bir mühazirə + bir seminar, hamı bir jurnalda, alt qrup sətirləri.
            merged = CourseOffering.objects.get(subject=self.same, period=self.period, group=parent)
            self.assertTrue(merged.is_active)
            self.assertEqual(merged.instructor_id, self.teacher.pk)
            self.assertEqual(Lesson.objects.filter(offering=merged).count(), 2)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=merged).count(), 10)
            sections = dict(SeminarGroup.objects.filter(offering=merged).values_list("unit_id", "number"))
            self.assertEqual(set(sections), {self.f1.pk, self.f2.pk})
            for group in (self.f1, self.f2):
                numbers = set(
                    Enrollment.objects.filter(
                        offering=merged, student__in=self.students[group.pk], status="enrolled"
                    ).values_list("seminar_group", flat=True)
                )
                self.assertEqual(numbers, {sections[group.pk]})
                source = self._source(self.same, group)
                self.assertFalse(source.is_active)
                self.assertEqual(
                    LessonMark.objects.filter(lesson__offering=source).count(), 2 * len(self.students[group.pk])
                )
                self.assertFalse(Enrollment.objects.filter(offering=source, status="enrolled").exists())

            # Fərqli saatlı gün: iki ayrı seminar, hər biri öz alt qrupuna; ortaq gün — bir dərs.
            merged_diff = CourseOffering.objects.get(subject=self.diff, period=self.period, group=parent)
            day1 = Lesson.objects.filter(offering=merged_diff, date=DAY1).order_by("start_time")
            self.assertEqual(
                [(lesson.start_time, lesson.seminar_group) for lesson in day1],
                [
                    (T0900, sections_of(merged_diff)[self.f1.pk]),
                    (T1150, sections_of(merged_diff)[self.f2.pk]),
                ],
            )
            self.assertEqual(Lesson.objects.filter(offering=merged_diff, date=DAY3).count(), 1)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=merged_diff).count(), 10)

            # Bloklanmış ailə toxunulmur.
            self.assertFalse(CourseOffering.objects.filter(subject=self.blocked, group=parent).exists())
            for group in (self.f1, self.f2):
                self.assertTrue(self._source(self.blocked, group).is_active)
            self.assertNotIn(parent.pk, self.rows[self.blocked.pk].groups.values_list("pk", flat=True))
            # Yük sətri: ana qrup ƏLAVƏ olunur, alt qruplar və saatlar qalır.
            row = TeachingTaskRow.objects.get(pk=self.rows[self.same.pk].pk)
            self.assertEqual(set(row.groups.values_list("pk", flat=True)), {self.f1.pk, self.f2.pk, parent.pk})
            self.assertEqual(row.lecture_total, 30)

        counts, families, _batch = self._call("--apply")
        self.assertEqual(counts["parent_existing"], "1")
        self.assertEqual(counts["subgroups_already_linked"], "2")
        self.assertNotIn("families_merged", counts)
        self.assertEqual((families["dun-2"]["status"], families["oed-5"]["status"]), ("already_merged",) * 2)
        self.assertEqual(families["sah"]["status"], "blocked_family_instructors_differ")
        with bypass_rls():
            self.assertEqual(OrgUnit.objects.filter(organization=self.org, name="334F").count(), 1)

    def test_undo_restores_everything_and_reapply_revives(self):
        with bypass_rls():
            before = self._snapshot()
        _counts, _families, batch = self._call("--apply")
        counts, _families, _batch = self._call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(counts["undo_families"], "2")
        self.assertEqual((counts["undo_links_removed"], counts["undo_parent_archived"]), ("2", "1"))
        with bypass_rls():
            parent = self._parent()
            self.assertFalse(parent.is_active)
            self.assertFalse(CourseOffering.objects.filter(group=parent, is_active=True).exists())
            snapshot = self._snapshot()
            # Yeganə fərq: arxivdəki «334F» və passiv birləşmiş jurnalları (qalan hər şey əvvəlki kimi).
            self.assertEqual(snapshot[0], before[0] + 1)
            self.assertEqual(snapshot[1:], before[1:])
        counts, _families, _batch = self._call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(counts, {"undo_already_done": "1"})

        counts, families, batch2 = self._call("--apply")
        self.assertEqual((counts["parent_revived"], counts["targets_revived"]), ("1", "2"))
        self.assertEqual((families["dun-2"]["status"], families["oed-5"]["status"]), ("merged", "merged"))
        counts, _families, _batch = self._call("--apply", "--undo", f"--batch={batch2}")
        self.assertEqual((counts["undo_families"], counts["undo_targets_deactivated"]), ("2", "2"))
        with bypass_rls():
            self.assertFalse(self._parent().is_active)
            self.assertEqual(self._snapshot()[1:], before[1:])

    def test_undo_blocked_when_teacher_wrote_after_merge(self):
        _counts, _families, batch = self._call("--apply")
        with bypass_rls():
            merged = CourseOffering.objects.get(subject=self.same, group=self._parent())
            Lesson.objects.create(
                organization=self.org, offering=merged, date=DAY3, kind=LessonKind.LECTURE, hours=2, start_time=T0900
            )
        counts, _families, _batch = self._call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(counts["undo_blocked_post_merge_data"], "1")
        self.assertEqual(counts["undo_parent_kept_merged_family"], "1")
        with bypass_rls():
            self.assertTrue(self._parent().is_active)
            self.assertFalse(self._source(self.same, self.f1).is_active)
            self.assertTrue(self._source(self.diff, self.f1).is_active)  # o biri ailə geri qayıdıb

    def test_load_sync_keeps_retired_journals_and_targets_parent(self):
        from apps.workload.services.offering_sync import sync_task_offerings

        self._call("--apply")
        with bypass_rls():
            parent = self._parent()
            active_before = set(CourseOffering.objects.filter(organization=self.org).values_list("pk", "is_active"))
            report = sync_task_offerings(self.task, create=True)
            self.assertEqual(report["inactive_subgroup_journal"], 4)  # 2 fənn × 2 passiv alt qrup jurnalı
            self.assertEqual(report["created"], 0)
            merged = set(
                str(pk)
                for pk in CourseOffering.objects.filter(group=parent, is_active=True).values_list("pk", flat=True)
            )
            self.assertTrue(merged <= set(report["offering_ids"]))
            self.assertEqual(
                set(CourseOffering.objects.filter(organization=self.org).values_list("pk", "is_active")), active_before
            )

    def test_ambiguous_names_are_refused(self):
        with bypass_rls():
            OrgUnit.objects.create(
                organization=self.org, parent=self.specialty, name="334F", slug="x334f", unit_type=OrgUnitType.GROUP
            )
            OrgUnit.objects.create(
                organization=self.org, parent=self.specialty, name="334 F", slug="y334f", unit_type=OrgUnitType.GROUP
            )
            before = self._snapshot()
        with self.assertRaisesMessage(CommandError, "f334_merge_refused_parent_ambiguous"):
            self._call("--apply")
        with bypass_rls():
            self.assertEqual(self._snapshot(), before)
            OrgUnit.objects.filter(slug__in=["x334f", "y334f"]).delete()
            OrgUnit.objects.create(
                organization=self.org, parent=self.specialty, name="334 F1", slug="z334f1", unit_type=OrgUnitType.GROUP
            )
        with self.assertRaisesMessage(CommandError, "f334_merge_refused_subgroup_ambiguous"):
            self._call("--apply")

    def test_existing_parent_is_reused(self):
        with bypass_rls():
            parent = OrgUnit.objects.create(
                organization=self.org, parent=self.specialty, name="334F", slug="own334f", unit_type=OrgUnitType.GROUP
            )
        counts, _families, _batch = self._call("--apply")
        self.assertEqual((counts["parent_existing"], counts["subgroups_linked"]), ("1", "2"))
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.filter(group=parent, is_active=True).count(), 2)

    def test_bad_batch_and_undo_without_batch(self):
        with self.assertRaisesMessage(CommandError, "f334_merge_batch_invalid"):
            self._call("--batch=lsplit-20261126-000000-abcd")
        with self.assertRaisesMessage(CommandError, "f334_merge_undo_needs_batch"):
            self._call("--undo")


def sections_of(offering) -> dict:
    return dict(SeminarGroup.objects.filter(offering=offering).values_list("unit_id", "number"))
