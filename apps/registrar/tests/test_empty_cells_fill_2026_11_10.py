"""Sahib 2026-11-10: boş xanalar yalnız sistemdaxili mötəbər mənbədən — ``fill_empty_cells_20261110``.

* ``dedupe``: dərs yükü axınının yaratdığı BOŞ öz-qrup dublikatı azad edilir (xanalar «alt qrupdan əlavə» sətrindədir);
* ``sibling``: eyni dərsin (tarix + saat + növ + müəllim) xanası tələbənin tarixçə qeydiyyatından köçürülür;
  başqa saat / başqa müəllim / fərqli dəyərlər → yazılmır; səviyyə kohortunda eyni səviyyə ailəsi sayılır;
* defolt dry-run, ``--undo --batch`` yalnız həmin qaçışı geri qaytarır, xəta → ``CommandError`` kodu.
"""

import datetime
import io
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import empty_cells_fill_2026_11_10 as fill
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    LanguageLevelCohort,
    Lesson,
    LessonKind,
    LessonMark,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
LINE = re.compile(r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
ELEMENTARY = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
PRE = "Xarici dildə işgüzar və akademik kommunikasiya-1(pre-intermediate)"


class EmptyCellsFillTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.day = cls.today - datetime.timedelta(days=10)
        with bypass_rls():
            cls.actor = User.objects.create_user("ec_admin", "ec_admin@x.test", "pw", is_superuser=True)
            cls.org = Organization.objects.create(
                name="EC Univ", slug="ec-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.actor,
                status="active", is_active=True,
            )  # fmt: skip
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org, name="Payız", period_type=AcademicPeriodType.SEMESTER, academic_year="2026/2027",
                start_date=cls.today - datetime.timedelta(days=60), end_date=cls.today + datetime.timedelta(days=60),
                is_current=True,
            )  # fmt: skip
            cls.teacher = User.objects.create_user("ec_teacher", "ec_t@x.test", "pw")
            cls.other_teacher = User.objects.create_user("ec_teacher2", "ec_t2@x.test", "pw")
            for user in (cls.teacher, cls.other_teacher):
                cls._member(user, "teacher")
            cls.group_a = OrgUnit.objects.create(organization=cls.org, name="536 MU1", unit_type=OrgUnitType.GROUP)
            cls.group_b = OrgUnit.objects.create(organization=cls.org, name="536 MU2", unit_type=OrgUnitType.GROUP)
            subject = Subject.objects.create(organization=cls.org, code="EC-1", name="Mühasibatlığın əsasları")
            cls.off_a = cls._offering(subject, cls.group_a)
            cls.off_b = cls._offering(subject, cls.group_b)
            cls.dup, cls.moved, cls.plain = (cls._student(f"ec_st{i}") for i in range(3))

    @classmethod
    def _member(cls, user, role_name):
        role, _ = Role.objects.get_or_create(
            organization=cls.org, name=role_name, defaults={"display_name": role_name, "level": 50, "permissions": []}
        )
        Role.objects.filter(pk=role.pk).update(is_active=True, scope_type=RoleScopeType.ORGANIZATION)
        Membership.objects.get_or_create(organization=cls.org, user=user, role=role, defaults={"is_active": True})

    @classmethod
    def _student(cls, username):
        user = User.objects.create_user(username, f"{username}@x.test", "pw")
        cls._member(user, "student")
        return user

    @classmethod
    def _offering(cls, subject, group, teacher=None):
        return CourseOffering.objects.create(
            organization=cls.org, subject=subject, period=cls.period, group=group, instructor=teacher or cls.teacher
        )

    def _lesson(self, offering, kind=LessonKind.LECTURE, start="10:10", day=None, instructor=None):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day or self.day, kind=kind, hours=2,
            start_time=datetime.time.fromisoformat(start), instructor=instructor,
        )  # fmt: skip

    def _enroll(self, student, offering, **extra):
        return Enrollment.objects.create(organization=self.org, student=student, offering=offering, **extra)

    def _mark(self, lesson, enrollment, status="present", score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score,
            entered_by=self.teacher,
        )  # fmt: skip

    def _call(self, *extra):
        out = io.StringIO()
        call_command("fill_empty_cells_20261110", "--org", self.org.slug, "--actor", self.actor.username, *extra,
                     stdout=out)  # fmt: skip
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, LINE)
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
        return counts

    def _world(self):
        with bypass_rls():
            a1, b1 = self._lesson(self.off_a), self._lesson(self.off_b)
            a2 = self._lesson(self.off_a, LessonKind.SEMINAR, "11:50")
            b2 = self._lesson(self.off_b, LessonKind.SEMINAR, "11:50")
            b_other_time = self._lesson(self.off_b, LessonKind.SEMINAR, "13:35")
            a3 = self._lesson(self.off_a, LessonKind.LECTURE, "15:15", instructor=self.other_teacher)
            b3 = self._lesson(self.off_b, LessonKind.LECTURE, "15:15")
            # 1) dublikat: xanalar «alt qrupdan əlavə» sətrində (A), öz qrup (B) sətri boşdur
            guest = self._enroll(self.dup, self.off_a, source_group=self.group_b)
            twin = self._enroll(self.dup, self.off_b)
            self._mark(a1, guest)
            # 2) köçürülmüş: köhnə (dropped) A sətrində xanalar, B-də boş
            old = self._enroll(self.moved, self.off_a, status="dropped")
            new = self._enroll(self.moved, self.off_b)
            self._mark(a1, old, "absent")
            self._mark(a2, old, "present", 8)
            self._mark(a3, old, "present")  # başqa müəllimin dərsi — köçürülmür
            # 3) mənbəsiz tələbə: boş qalır (uydurulmur)
            plain = self._enroll(self.plain, self.off_b)
        return {"b1": b1, "b2": b2, "b_other_time": b_other_time, "b3": b3, "twin": twin, "new": new, "plain": plain}

    def test_dry_run_apply_idempotent_and_undo_by_batch(self):
        world = self._world()
        counts = self._call()
        self.assertEqual((counts["dedupe_released"], counts["sibling_filled"]), ("1", "2"))
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=world["twin"].pk).status, "enrolled")  # dry-run
            self.assertFalse(LessonMark.objects.filter(enrollment=world["new"]).exists())

        counts = self._call("--apply")
        self.assertEqual((counts["dedupe_released"], counts["sibling_filled"]), ("1", "2"))
        batch = counts["batch"]
        with bypass_rls():
            twin = Enrollment.objects.get(pk=world["twin"].pk)
            self.assertEqual(twin.status, "dropped")
            new_marks = {m.lesson_id: m for m in LessonMark.objects.filter(enrollment=world["new"])}
            self.assertEqual(set(new_marks), {world["b1"].pk, world["b2"].pk})
            self.assertEqual(new_marks[world["b1"].pk].status, "absent")
            self.assertEqual((new_marks[world["b2"].pk].status, new_marks[world["b2"].pk].score), ("present", 8))
            self.assertEqual(new_marks[world["b2"].pk].entered_by_id, self.teacher.pk)
            self.assertFalse(LessonMark.objects.filter(enrollment=world["plain"]).exists())
            self.assertEqual(Enrollment.objects.get(pk=world["new"].pk).absence_hours, 2)

        again = self._call("--apply")
        self.assertNotIn("sibling_filled", again)
        self.assertNotIn("dedupe_released", again)

        counts = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual((counts["undo_cells_deleted"], counts["undo_released_restored"]), ("2", "1"))
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=world["twin"].pk).status, "enrolled")
            self.assertFalse(LessonMark.objects.filter(enrollment=world["new"]).exists())
            self.assertEqual(Enrollment.objects.get(pk=world["new"].pk).absence_hours, 0)

    def test_undo_keeps_teacher_changed_cell(self):
        world = self._world()
        batch = self._call("--apply", "--only", "sibling")["batch"]
        with bypass_rls():
            LessonMark.objects.filter(enrollment=world["new"], lesson=world["b1"]).update(status="present")
        counts = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual((counts["undo_cells_deleted"], counts["undo_cells_changed_kept"]), ("1", "1"))

    def test_conflicting_sources_are_not_written(self):
        with bypass_rls():
            b1 = self._lesson(self.off_b)
            a1 = self._lesson(self.off_a)
            third = self._offering(self.off_a.subject, OrgUnit.objects.create(
                organization=self.org, name="536 MU", unit_type=OrgUnitType.GROUP))  # fmt: skip
            c1 = self._lesson(third)
            self._mark(a1, self._enroll(self.moved, self.off_a, status="dropped"), "present")
            self._mark(c1, self._enroll(self.moved, third, status="dropped"), "absent")
            target = self._enroll(self.moved, self.off_b)
        counts = self._call("--apply", "--only", "sibling")
        self.assertEqual(counts["sibling_ambiguous"], "1")
        with bypass_rls():
            self.assertFalse(LessonMark.objects.filter(lesson=b1, enrollment=target).exists())

    def test_level_cohort_takes_same_family_same_teacher_session(self):
        with bypass_rls():
            department = OrgUnit.objects.create(organization=self.org, name="Xarici dillər", unit_type="department")
            cohort_group = OrgUnit.objects.create(
                organization=self.org, name="E-26 · elementary", unit_type=OrgUnitType.GROUP, parent=department,
                settings={"language_level_cohort": True},
            )  # fmt: skip
            elementary = Subject.objects.create(organization=self.org, code="EC-E", name=ELEMENTARY)
            pre = Subject.objects.create(organization=self.org, code="EC-P", name=PRE)
            cohort_offering = self._offering(elementary, cohort_group)
            CourseOffering.objects.filter(pk=cohort_offering.pk).update(lesson_hours=60)
            LanguageLevelCohort.objects.create(
                organization=self.org, department=department, group=cohort_group, offering=cohort_offering,
                period=self.period, name="E-26", family="xarici dildə işgüzar və akademik kommunikasiya-1",
                level="elementary", created_by=self.actor, seminar_hours=60,
            )  # fmt: skip
            source_offering = self._offering(pre, self.group_a)
            source_offering.is_active = False
            source_offering.save(update_fields=["is_active"])
            src = self._lesson(source_offering, LessonKind.SEMINAR, "08:30")
            dst = self._lesson(cohort_offering, LessonKind.SEMINAR, "08:30")
            self._mark(src, self._enroll(self.moved, source_offering, status="dropped"), "present", 9)
            target = self._enroll(self.moved, cohort_offering, source_group=self.group_a)
        counts = self._call("--apply", "--only", "sibling")
        self.assertEqual(counts["sibling_filled_cohort"], "1")
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=dst, enrollment=target)
            self.assertEqual((mark.status, mark.score), ("present", 9))

    def test_unexpected_error_becomes_command_error_code(self):
        with mock.patch.object(fill, "run", side_effect=ValueError("Boom 7")):
            with self.assertRaisesMessage(CommandError, "empty_cells_failed_valueerror_boom_7"):
                self._call("--apply")

    def test_undo_requires_valid_batch(self):
        with self.assertRaisesMessage(CommandError, "empty_cells_undo_needs_batch"):
            self._call("--undo")
        with self.assertRaisesMessage(CommandError, "empty_cells_batch_invalid"):
            self._call("--undo", "--batch", "x; drop")
