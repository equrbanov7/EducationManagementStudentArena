"""Sahib 2026-11-07: seminar alt qrupları BİR jurnal daxilində + jurnal bölmələri.

* alt qruplu seminar dərsi yalnız öz alt qrupunun tələbələrinindir (yazı rədd, qrid «·», saat həddi tələbə başına);
  alt qrup seçimi İSTƏYƏ BAĞLIDIR (boş = bütün qrup, köhnə davranış); yalnız seminar dərsinə aiddir;
* jurnal səhifəsi: alt qrup seçimi, bölmə düymələri («Mühazirə», «K1 · Seminar», «K1 · Lab-1»), bölünməmiş jurnalda yox;
* ``apply_seminar_groups``: reyestr ailəsindən (``parent_group``) alt qruplar, tələbə yerləşdirmə, lab adları;
  ikidən az alt qrup → atlanır; defolt dry-run, idempotent, mövcud dəyər üzərinə yazılmır; prod-data-ops-a qoşulub.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar import gradebook, journal_activation, lab_groups, seminar_groups
from apps.registrar.models import (
    Curriculum,
    Enrollment,
    LabGroup,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    SeminarGroup,
    StudentAcademicRecord,
)
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, User, _LabWorld
from core.constants import OrgUnitType
from core.rls import bypass_rls


class SeminarGroupRulesTest(SimpleTestCase):
    def test_applies_checks_both_splits(self):
        k1 = SimpleNamespace(lab_group=1, seminar_group=1)
        self.assertTrue(lab_groups.applies(SimpleNamespace(lab_group=None, seminar_group=1), k1))
        self.assertFalse(lab_groups.applies(SimpleNamespace(lab_group=None, seminar_group=2), k1))
        self.assertTrue(lab_groups.applies(SimpleNamespace(lab_group=None, seminar_group=None), k1))
        self.assertFalse(lab_groups.applies(SimpleNamespace(lab_group=2, seminar_group=None), k1))

    def test_per_student_hours_takes_one_seminar_subgroup(self):
        lessons = [
            SimpleNamespace(hours=2, lab_group=None, seminar_group=None),
            SimpleNamespace(hours=2, lab_group=None, seminar_group=1),
            SimpleNamespace(hours=2, lab_group=None, seminar_group=1),
            SimpleNamespace(hours=2, lab_group=None, seminar_group=2),
            SimpleNamespace(hours=2, lab_group=1, seminar_group=None),
        ]
        self.assertEqual(lab_groups.per_student_hours(lessons), 2 + 4 + 2)
        self.assertEqual(lab_groups.per_student_hours(lessons, extra_hours=2, extra_seminar_group=2), 8)
        self.assertEqual(lab_groups.per_student_hours(lessons, extra_hours=2, extra_seminar_group=1), 10)

    def test_parse(self):
        self.assertIsNone(seminar_groups.parse(""))
        self.assertEqual(seminar_groups.parse("2"), 2)
        for raw in ("0", "x", "10"):
            with self.assertRaises(seminar_groups.SeminarGroupError):
                seminar_groups.parse(raw)


class SeminarGroupJournalTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            for number, name in ((1, "LAB-G1 K1"), (2, "LAB-G1 K2")):
                SeminarGroup.objects.create(organization=self.org, offering=self.offering, number=number, name=name)
            Enrollment.objects.filter(pk=self.e1.pk).update(seminar_group=1)
            Enrollment.objects.filter(pk=self.e2.pk).update(seminar_group=2)
        self.e1.refresh_from_db()
        self.e2.refresh_from_db()

    def _sem(self, group=None, kind=LessonKind.SEMINAR):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org, offering=self.offering, date=self.today, kind=kind, hours=2, seminar_group=group
            )

    def test_save_marks_rejects_other_subgroup_cells(self):
        k2 = self._sem(2)
        entries = [
            {"lesson_id": str(k2.pk), "enrollment_id": str(self.e1.pk), "status": "absent"},
            {"lesson_id": str(k2.pk), "enrollment_id": str(self.e2.pk), "status": "absent"},
        ]
        with bypass_rls():
            result = gradebook.save_marks(offering=self._fresh(), entries=entries, enforce_day=False, report=True)
            self.assertEqual((result["written"], result["rejected"]), (1, 1))
            self.assertFalse(LessonMark.objects.filter(lesson=k2, enrollment=self.e1).exists())

    def test_grid_closes_other_subgroup_and_labels(self):
        self._sem(1)
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self._fresh())
        rows = {row["enrollment"].pk: row for row in journal["rows"]}
        self.assertFalse(rows[self.e1.pk]["cells"][0].get("off_group", False))
        self.assertTrue(rows[self.e2.pk]["cells"][0]["off_group"])
        self.assertEqual(journal["lesson_meta"][0]["seminar_group_label"], "LAB-G1 K1")
        self.assertEqual(rows[self.e2.pk]["seminar_group_label"], "LAB-G1 K2")
        labels = [section["label"] for section in journal["journal_sections"]]
        self.assertIn("LAB-G1 K1 · Seminar", labels)
        self.assertIn("LAB-G1 · Mühazirə", labels)

    def test_journal_page_renders_picker_and_sections(self):
        self._sem(2)
        response = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(response, 'name="lesson_seminar_group"')
        self.assertContains(response, "registrar/js/journal_lesson_seminar_group.js")
        self.assertContains(response, "registrar/js/journal_sections.js")
        self.assertContains(response, "data-jd-section")
        self.assertContains(response, 'data-lesson-seminar-group="2"')

    def test_unsplit_journal_has_no_seminar_picker_or_sections(self):
        with bypass_rls():
            SeminarGroup.objects.all().delete()
            Enrollment.objects.filter(offering=self.offering).update(seminar_group=None, lab_group=None)
        response = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertNotContains(response, 'name="lesson_seminar_group"')
        self.assertNotContains(response, "data-jd-section")

    def _post_lesson(self, **fields):
        data = {
            "action": "add_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": LessonKind.SEMINAR,
            "lesson_hours": "2",
            "lesson_time": "08:30|10:00",
        }
        data.update(fields)
        return self._client(self.teacher).post(reverse("registrar:journal_detail", args=[self.offering.id]), data)

    def test_new_seminar_lesson_subgroup_is_optional(self):
        self._post_lesson()
        self.assertIsNone(Lesson.objects.get(offering=self.offering).seminar_group)
        self._post_lesson(lesson_seminar_group="3", lesson_time="10:10|11:40")
        self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 1)
        self._post_lesson(lesson_seminar_group="2", lesson_time="10:10|11:40")
        self.assertEqual(Lesson.objects.filter(offering=self.offering, seminar_group=2).count(), 1)

    def test_subgroup_only_on_seminar_lessons(self):
        with self.assertRaises(gradebook.LessonRuleError), bypass_rls():
            gradebook.create_lesson(
                offering=self._fresh(), date=self.today, kind=LessonKind.LECTURE, seminar_group=1, allow_past=True
            )

    def test_edit_rules(self):
        lesson = self._sem(1)
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.e1, status="present")
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=lesson, seminar_group=2)
            gradebook.update_lesson(lesson=lesson, kind=LessonKind.LECTURE)
            self.assertIsNone(Lesson.objects.get(pk=lesson.pk).seminar_group)

    def test_hours_cap_is_per_student(self):
        self._sem(kind=LessonKind.LECTURE)
        self._sem(1)
        self._sem(2)
        # 2 (mühazirə) + 2 (bir alt qrup) = 4; həddi 6.
        self.assertEqual(journal_activation.hours_cap_error(self._fresh(), 2, seminar_group=2), "")
        self._sem(2)
        self.assertNotEqual(journal_activation.hours_cap_error(self._fresh(), 2, seminar_group=2), "")
        self.assertEqual(journal_activation.hours_cap_error(self._fresh(), 2, seminar_group=1), "")


class ApplySeminarGroupsCommandTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            specialty = OrgUnit.objects.create(
                organization=self.org, name="SP", slug="sem-sp", unit_type=OrgUnitType.SPECIALTY
            )
            OrgUnit.objects.filter(pk=self.group.pk).update(parent=specialty, name="234 K")
            self.group.refresh_from_db()
            self.k1, self.k2 = (
                OrgUnit.objects.create(
                    organization=self.org,
                    name=name,
                    slug=f"sem-{name[-2:].lower()}",
                    unit_type=OrgUnitType.GROUP,
                    parent=specialty,
                    settings={"parent_group": str(self.group.pk)},
                )
                for name in ("234 K1", "234 K2")
            )
            self.program = Program.objects.create(organization=self.org, code="SEM", name="Sem")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2026
            )

    def _records(self, *units):
        with bypass_rls():
            for student, unit in zip(self.students, units):
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=unit,
                    admission_year=2026,
                )

    def _call(self, *extra):
        out = io.StringIO()
        call_command("apply_seminar_groups", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out)
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^lab_groups: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def test_dry_run_apply_idempotent(self):
        self._records(self.k1, self.k2, self.group)
        dry = self._call()
        self.assertEqual(
            {k: dry.get(k) for k in ("journals", "seminar_groups_created", "students_placed", "lab_named")},
            {"journals": "1", "seminar_groups_created": "2", "students_placed": "2", "lab_named": "2"},
        )
        with bypass_rls():
            self.assertFalse(SeminarGroup.objects.exists())
        self._call("--apply")
        with bypass_rls():
            self.assertEqual(
                dict(SeminarGroup.objects.filter(offering=self.offering).values_list("number", "name")),
                {1: "234 K1", 2: "234 K2"},
            )
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).seminar_group, 1)
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).seminar_group, 2)
            self.assertIsNone(Enrollment.objects.get(pk=self.e0.pk).seminar_group)
            self.assertEqual(
                dict(LabGroup.objects.filter(offering=self.offering).values_list("number", "name")),
                {1: "234 K1 · Lab-1", 2: "234 K2 · Lab-2"},
            )
        again = self._call("--apply")
        self.assertEqual((again["students_already"], again.get("students_placed")), ("2", None))

    def test_single_subgroup_is_skipped(self):
        self._records(self.k1, self.k1, self.group)
        self.assertEqual(self._call("--apply")["journals_single_subgroup_skipped"], "1")
        with bypass_rls():
            self.assertFalse(SeminarGroup.objects.exists())

    def test_existing_value_is_not_overwritten(self):
        self._records(self.k1, self.k2, self.group)
        with bypass_rls():
            Enrollment.objects.filter(pk=self.e1.pk).update(seminar_group=2)
        self.assertEqual(self._call("--apply")["students_conflict"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).seminar_group, 2)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - apply_seminar_groups\n", text)
        self.assertIn('[ "$COMMAND" = "apply_seminar_groups" ]', text)


__all__ = ["User"]
