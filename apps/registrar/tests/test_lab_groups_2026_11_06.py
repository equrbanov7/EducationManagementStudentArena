"""Sahib 2026-11-06: laboratoriya qrupları (Lab-1 / Lab-2) BİR jurnal daxilində.

Nəyi qoruyur
------------
* qruplu lab dərsi yalnız öz qrupunun tələbələrinindir: başqa qrupun xanası yazılmır (``save_marks`` rədd edir),
  qridda bağlı «·» xanadır, sütun özətinin məxrəci qrupun sayıdır; mühazirə / seminar bütün qrupladır;
* qayıb saatı tələbənin öz xanalarındandır — Lab-2 dərsi Lab-1 tələbəsinin qayıbına düşmür;
* fənnin saat həddi tələbə başınadır (qrupsuz dərslər + bir lab qrupu);
* «Yeni dərs»: bölünmüş jurnalda lab dərsinin qrupu məcburidir, qrup yalnız lab dərsinə və mövcud qrupa aiddir;
  redaktə qrupu dəyişə bilər, amma başqa qrupun xanası varsa yox;
* ``apply_lab_groups_20261106`` əmri: defolt dry-run, ``--apply``, idempotent, başqa dəyərin üzərinə yazmır,
  köçürülmüş lab dərsini xanalarının qrupuna bağlayır, stdout-da yalnız saylar; prod-data-ops-a qoşulub.
"""

from __future__ import annotations

import datetime
import io
import pathlib
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import gradebook, journal_activation, lab_groups
from apps.registrar import lab_groups_apply_2026_11_06 as apply_plan
from apps.registrar import services as registrar_services
from apps.registrar.models import Enrollment, JournalShare, Lesson, LessonKind, LessonMark, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class LabGroupRulesTest(SimpleTestCase):
    def test_applies_only_to_own_group(self):
        lesson = SimpleNamespace(lab_group=2)
        self.assertTrue(lab_groups.applies(lesson, SimpleNamespace(lab_group=2)))
        self.assertFalse(lab_groups.applies(lesson, SimpleNamespace(lab_group=1)))
        self.assertFalse(lab_groups.applies(lesson, SimpleNamespace(lab_group=None)))
        self.assertTrue(lab_groups.applies(SimpleNamespace(lab_group=None), SimpleNamespace(lab_group=1)))

    def test_per_student_hours_counts_one_lab_group(self):
        lessons = [
            SimpleNamespace(hours=2, lab_group=None),
            SimpleNamespace(hours=2, lab_group=1),
            SimpleNamespace(hours=2, lab_group=1),
            SimpleNamespace(hours=2, lab_group=2),
        ]
        self.assertEqual(lab_groups.per_student_hours(lessons), 6)
        self.assertEqual(lab_groups.per_student_hours(lessons, extra_hours=2, extra_group=2), 6)
        self.assertEqual(lab_groups.per_student_hours(lessons, extra_hours=2, extra_group=1), 8)
        self.assertEqual(lab_groups.per_student_hours(lessons, extra_hours=2), 8)

    def test_parse(self):
        self.assertIsNone(lab_groups.parse(""))
        self.assertEqual(lab_groups.parse("2"), 2)
        for raw in ("0", "x", "-1", "10"):
            with self.assertRaises(lab_groups.LabGroupError):
                lab_groups.parse(raw)


class _LabWorld:
    """Bir açılış: Lab-1, Lab-2 və qrupsuz tələbə (müəllim — açılışın sahibi)."""

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        with bypass_rls():
            cls.owner = User.objects.create_user("lab_owner", "lab_owner@x.test", "pw")
            cls.org = Organization.objects.create(
                name="LAB Univ",
                slug="lab-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="LAB-G1", slug="lab-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.today - datetime.timedelta(days=60),
                end_date=cls.today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.teacher = User.objects.create_user("lab_teacher", "lab_teacher@x.test", "pw")
            cls._member(cls.teacher, "teacher", ["grade.input"])
            subject = Subject.objects.create(organization=cls.org, code="LAB101", name="Ümumi kimya")
            cls.offering = registrar_services.get_or_create_offering(
                organization=cls.org, subject=subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 6
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.students = []
            for index in range(3):
                student = User.objects.create_user(f"lab_st{index}", f"lab_st{index}@x.test", "pw")
                cls._member(student, "student", [])
                cls.students.append(student)
            cls.e1, cls.e2, cls.e0 = (
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering, lab_group=group)
                for student, group in zip(cls.students, (1, 2, None))
            )

    @classmethod
    def _member(cls, user, role_name, permissions):
        role, _created = Role.objects.get_or_create(
            organization=cls.org,
            name=role_name,
            defaults={"display_name": role_name.title(), "level": 50, "permissions": list(permissions)},
        )
        Role.objects.filter(pk=role.pk).update(
            is_active=True, permissions=list(permissions), scope_type=RoleScopeType.ORGANIZATION
        )
        Membership.objects.get_or_create(organization=cls.org, user=user, role=role, defaults={"is_active": True})

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fresh(self):
        return type(self.offering).objects.get(pk=self.offering.pk)

    def _lesson(self, kind=LessonKind.LAB, lab_group=None, hours=2):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today,
                kind=kind,
                hours=hours,
                lab_group=lab_group,
            )


class LabGroupJournalTest(_LabWorld, TestCase):
    # ── yazı ─────────────────────────────────────────────────────────────────
    def test_save_marks_rejects_other_lab_group_cells(self):
        lab2 = self._lesson(lab_group=2)
        lecture = self._lesson(kind=LessonKind.LECTURE)
        entries = [
            {"lesson_id": str(lab2.pk), "enrollment_id": str(self.e1.pk), "status": "absent"},
            {"lesson_id": str(lab2.pk), "enrollment_id": str(self.e2.pk), "status": "absent"},
            {"lesson_id": str(lecture.pk), "enrollment_id": str(self.e1.pk), "status": "present"},
        ]
        with bypass_rls():
            result = gradebook.save_marks(offering=self._fresh(), entries=entries, enforce_day=False, report=True)
            self.assertEqual((result["written"], result["rejected"]), (2, 1))
            self.assertFalse(LessonMark.objects.filter(lesson=lab2, enrollment=self.e1).exists())
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).absence_hours, 2)
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).absence_hours, 0)

    # ── qrid ─────────────────────────────────────────────────────────────────
    def test_grid_shows_other_group_cells_as_closed_and_counts_the_group(self):
        lab1 = self._lesson(lab_group=1)
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self._fresh())
        rows = {row["enrollment"].pk: row for row in journal["rows"]}
        self.assertTrue(journal["has_lab_groups"])
        self.assertFalse(rows[self.e1.pk]["cells"][0].get("off_group", False))
        self.assertTrue(rows[self.e1.pk]["cells"][0]["writable"])
        self.assertTrue(rows[self.e2.pk]["cells"][0]["off_group"])
        self.assertFalse(rows[self.e2.pk]["cells"][0]["writable"])
        self.assertEqual(rows[self.e1.pk]["lab_group_label"], "Lab-1")
        self.assertTrue(rows[self.e0.pk]["lab_group_missing"])
        meta = journal["lesson_meta"][0]
        self.assertEqual((meta["lab_group_label"], meta["summary"]["total"]), ("Lab-1", 1))
        self.assertEqual(lab1.pk, meta["lesson"].pk)

    def test_data_recovery_mode_keeps_other_group_cells_closed(self):
        from apps.registrar import journal_full_edit

        self._lesson(lab_group=1)
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self._fresh())
        journal_full_edit._unlock_grid(journal, journal_locked=False)
        rows = {row["enrollment"].pk: row for row in journal["rows"]}
        self.assertFalse(rows[self.e2.pk]["cells"][0]["writable"])
        self.assertTrue(rows[self.e1.pk]["cells"][0]["writable"])

    def test_journal_page_renders_lab_group_picker_and_closed_cells(self):
        self._lesson(lab_group=2)
        response = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(response, 'name="lesson_lab_group"')
        self.assertContains(response, "registrar/js/journal_lesson_lab_group.js")
        self.assertContains(response, "jd2-ro--offgroup")
        self.assertContains(response, 'data-lesson-lab-group="2"')

    def test_unsplit_journal_has_no_picker(self):
        with bypass_rls():
            Enrollment.objects.filter(offering=self.offering).update(lab_group=None)
        response = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertNotContains(response, 'name="lesson_lab_group"')
        self.assertNotContains(response, "journal_lesson_lab_group.js")

    # ── «Yeni dərs» / redaktə ────────────────────────────────────────────────
    def _post_lesson(self, **fields):
        data = {
            "action": "add_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": LessonKind.LAB,
            "lesson_hours": "2",
            "lesson_time": "08:30|10:00",
        }
        data.update(fields)
        return self._client(self.teacher).post(reverse("registrar:journal_detail", args=[self.offering.id]), data)

    def test_new_lab_lesson_requires_a_group_in_a_split_journal(self):
        self._post_lesson()
        self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())
        self._post_lesson(lesson_lab_group="3")
        self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())
        self._post_lesson(lesson_lab_group="2")
        self.assertEqual(Lesson.objects.get(offering=self.offering).lab_group, 2)

    def test_group_only_on_lab_lessons(self):
        with self.assertRaises(gradebook.LessonRuleError), bypass_rls():
            gradebook.create_lesson(
                offering=self._fresh(), date=self.today, kind=LessonKind.SEMINAR, lab_group=1, allow_past=True
            )

    def test_edit_cannot_move_a_lesson_with_marks_to_another_group(self):
        lesson = self._lesson(lab_group=1)
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.e1, status="present")
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=lesson, lab_group=2)
            empty = self._lesson(lab_group=1)
            self.assertTrue(gradebook.update_lesson(lesson=empty, lab_group=2))
            self.assertEqual(Lesson.objects.get(pk=empty.pk).lab_group, 2)

    def test_kind_change_away_from_lab_drops_the_group(self):
        lesson = self._lesson(lab_group=1)
        with bypass_rls():
            gradebook.update_lesson(lesson=lesson, kind=LessonKind.SEMINAR)
            self.assertIsNone(Lesson.objects.get(pk=lesson.pk).lab_group)

    def test_hours_cap_is_per_student(self):
        self._lesson(kind=LessonKind.LECTURE)
        self._lesson(lab_group=1)
        self._lesson(lab_group=2)
        offering = self._fresh()
        # 2 (mühazirə) + 2 (bir lab qrupu) = 4; həddi 6 — hər qrupa daha bir lab dərsi sığır.
        self.assertEqual(journal_activation.hours_cap_error(offering, 2, lab_group=2), "")
        self._lesson(lab_group=2)
        self.assertNotEqual(journal_activation.hours_cap_error(self._fresh(), 2, lab_group=2), "")
        self.assertEqual(journal_activation.hours_cap_error(self._fresh(), 2, lab_group=1), "")
        self.assertNotEqual(journal_activation.hours_cap_error(self._fresh(), 2), "")


class ApplyLabGroupsCommandTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            Enrollment.objects.filter(offering=self.offering).update(lab_group=None)
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
        st1, st2, st0 = (student.pk for student in self.students)
        plans = (
            {
                "key": "chem",
                "offering": str(self.offering.pk),
                "groups": {1: (st1, 999999), 2: (st2,)},
                "lab_teacher": self.teacher.pk,
            },
        )
        patch = mock.patch.object(apply_plan, "PLANS", plans)
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "apply_lab_groups_20261106", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        text = out.getvalue()
        counts = {}
        for line in text.splitlines():
            self.assertTrue(line.startswith("lab_groups: "), line)
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def test_dry_run_apply_idempotent(self):
        legacy_lab = self._lesson()
        mixed = self._lesson()
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=legacy_lab, enrollment=self.e2, status="present")
            LessonMark.objects.create(organization=self.org, lesson=mixed, enrollment=self.e1, status="present")
            LessonMark.objects.create(organization=self.org, lesson=mixed, enrollment=self.e2, status="present")
            share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.teacher, kinds=["seminar"]
            )
        dry = self._call()
        self.assertEqual(
            {key: dry.get(key) for key in ("chem_lab1", "chem_lab2", "chem_not_enrolled", "chem_ungrouped")},
            {"chem_lab1": "1", "chem_lab2": "1", "chem_not_enrolled": "1", "chem_ungrouped": "1"},
        )
        self.assertEqual(
            (dry["chem_lesson_lab2"], dry["chem_lesson_mixed"], dry["chem_share_lab_added"]), ("1", "1", "1")
        )
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, lab_group__isnull=False).exists())
        self._call("--apply")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).lab_group, 1)
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).lab_group, 2)
            self.assertIsNone(Enrollment.objects.get(pk=self.e0.pk).lab_group)
            self.assertEqual(Lesson.objects.get(pk=legacy_lab.pk).lab_group, 2)
            self.assertIsNone(Lesson.objects.get(pk=mixed.pk).lab_group)
            self.assertEqual(JournalShare.objects.get(pk=share.pk).kinds, ["seminar", "lab"])
        again = self._call("--apply")
        self.assertEqual(
            (again["chem_already"], again["chem_lesson_already"], again["chem_share_already"]), ("2", "1", "1")
        )
        self.assertNotIn("chem_lab1", again)

    def test_never_overwrites_another_group(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.e1.pk).update(lab_group=2)
        counts = self._call("--apply")
        self.assertEqual(counts["chem_conflict"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).lab_group, 2)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - apply_lab_groups_20261106\n", text)
        self.assertIn('[ "$COMMAND" = "apply_lab_groups_20261106" ]', text)
        self.assertIn("|lab_groups): ", text)


class ApplyLabGroupsPlanTest(SimpleTestCase):
    def test_plan_matches_the_legacy_lists(self):
        sizes = {plan["key"]: tuple(len(plan["groups"][group]) for group in (1, 2)) for plan in apply_plan.PLANS}
        self.assertEqual(sizes, {"bio": (19, 18), "chem": (20, 19), "anal": (18, 18)})
        for plan in apply_plan.PLANS:
            one, two = (set(plan["groups"][group]) for group in (1, 2))
            self.assertFalse(one & two, plan["key"])
