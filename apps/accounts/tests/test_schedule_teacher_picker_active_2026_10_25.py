"""«Cədvəl idarəetməsi» müəllim seçicisi — seçilmiş dövrdə AKTİV müəllimlər (sahib, 2026-10-25).

Sahibin tələbi: «Müəllim axtar yerində ancaq AKTİV müəllimlər görünsün — həmin ildəki. Köhnə ilə baxanda,
köhnədə aktiv idisə, ona görünə bilər.»

Nəyi qoruyur
------------
* CARİ dövr: bloklanmış (``is_active=False``), arxivlənmiş (``access_state``), üzvlüyü passiv və o dövrdə
  heç bir yükü (bölgü / açılış / dərs / slot) olmayan müəllim seçicidə YOXDUR;
* dövr müəllimi dörd mənbədən gəlir: bölgü (``TeacherAssignment``), jurnal sahibi, dərsin müəllimi, slot müəllimi;
* BİTMİŞ dövr: o vaxt dərs deyən hər kəs (hesabı indi bloklanmış olsa da) görünür, yükü olmayan görünmür;
* əhatə fail-closed: koordinator əhatəsindən kənar qrupun bölgüsündəki müəllimi görmür, sahib görür;
* HTTP: bloklanmış müəllimin ``sm_teacher`` dərin linki seçim yaratmır.
"""

from __future__ import annotations

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar import schedule_manage, services
from apps.registrar.models import Lesson, ScheduleSlot, Subject
from apps.workload.constants import Activity
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrgUnitType
from core.rls import bypass_rls

from .test_schedule_editor_ui import ScheduleEditorUIBase, User


def _rows(actor, org, period):
    """Görünüşün (``_selection``) çağırdığı eyni zəncir: əhatəli açılışlar + bölgü → seçici sətirləri."""
    perm = schedule_manage.SCHEDULE_PERMISSION
    offerings = schedule_manage.scoped_offerings(actor, org, period=period, permission=perm, widened=True)
    assignments = schedule_manage.scoped_assignments(actor, org, period=period, permission=perm, widened=True)
    return schedule_manage.scoped_teacher_rows(offerings, organization=org, period=period, assignments=assignments)


class PickerBase(ScheduleEditorUIBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.past_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2023/2024 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date=datetime.date.today() - datetime.timedelta(days=700),
                end_date=datetime.date.today() - datetime.timedelta(days=600),
                is_current=False,
            )
            cls.subject2 = Subject.objects.create(organization=cls.org, code="CS202", name="Alqoritmlər")
            cls.chair = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Kafedra",
                slug="sedtp-chair",
                unit_type=OrgUnitType.CHAIR,
            )

    @classmethod
    def _user(cls, name, *, membership=True):
        user = User.objects.create_user(f"sedtp_{name}", f"sedtp_{name}@qku.edu.az", "pw", first_name=name.title())
        if membership:
            Membership.objects.create(
                user=user, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_primary=True, is_active=True
            )
        return user

    def _ids(self, actor=None, period=None):
        return {row["id"] for row in _rows(actor or self.coordinator, self.org, period or self.period)}

    def _offering(self, instructor, *, period=None, group=None, subject=None):
        offering = services.get_or_create_offering(
            organization=self.org,
            subject=subject or self.subject2,
            period=period or self.period,
            group=group or self.group,
        )
        offering.instructor = instructor
        offering.save(update_fields=["instructor"])
        return offering

    def _assign(self, teacher, *, group, period=None, academic_year="2025/2026", chair=None):
        task, _created = TeachingTask.objects.get_or_create(
            organization=self.org, chair=chair or self.chair, academic_year=academic_year
        )
        row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            period=period,
            subject=self.subject2,
            lecture_plan=30,
            lecture_total=30,
            total_hours=30,
        )
        row.groups.set([group])
        return TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=teacher, activity=Activity.LECTURE, hours=30
        )


class CurrentPeriodTest(PickerBase):
    def test_active_teacher_with_an_offering_is_listed(self):
        with bypass_rls():
            self.assertIn(str(self.teacher.pk), self._ids())

    def test_blocked_teacher_is_hidden_in_the_current_period(self):
        blocked = self._user("blocked")
        with bypass_rls():
            self._offering(blocked)
            self.assertIn(str(blocked.pk), self._ids())
            blocked.is_active = False
            blocked.save(update_fields=["is_active"])
            self.assertNotIn(str(blocked.pk), self._ids())

    def test_archived_and_deleted_profiles_are_hidden(self):
        archived, deleted = self._user("archived"), self._user("deleted")
        with bypass_rls():
            self._offering(archived, group=self.group)
            self._offering(deleted, group=self.group_b)
            archived.profile.access_state = "archived"
            archived.profile.save(update_fields=["access_state"])
            deleted.profile.is_deleted = True
            deleted.profile.save(update_fields=["is_deleted"])
            ids = self._ids()
        self.assertNotIn(str(archived.pk), ids)
        self.assertNotIn(str(deleted.pk), ids)

    def test_teacher_without_an_active_membership_is_hidden(self):
        ex_member = self._user("exmember")
        with bypass_rls():
            self._offering(ex_member)
            Membership.objects.filter(user=ex_member, organization=self.org).update(is_active=False)
            self.assertNotIn(str(ex_member.pk), self._ids())

    def test_teacher_without_any_load_this_period_is_hidden(self):
        idle = self._user("idle")
        with bypass_rls():
            self.assertNotIn(str(idle.pk), self._ids())
            # Başqa (bitmiş) dövrdəki yük cari dövrdə SAYILMIR.
            self._offering(idle, period=self.past_period)
            self.assertNotIn(str(idle.pk), self._ids())

    def test_each_source_makes_a_teacher_active(self):
        by_assignment = self._user("byassign")
        by_lesson = self._user("bylesson")
        by_slot = self._user("byslot")
        with bypass_rls():
            self._assign(by_assignment, group=self.group, period=self.period)
            lesson_offering = self._offering(self.teacher, group=self.group)
            Lesson.objects.create(
                organization=self.org, offering=lesson_offering, date=datetime.date.today(), instructor=by_lesson
            )
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self._offering(self.teacher, group=self.group_b),
                weekday=2,
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                instructor=by_slot,
            )
            ids = self._ids()
        for user in (by_assignment, by_lesson, by_slot):
            self.assertIn(str(user.pk), ids, user.username)

    def test_assignment_without_row_period_matches_by_academic_year(self):
        year_only, other_year = self._user("yearonly"), self._user("otheryear")
        with bypass_rls():
            self._assign(year_only, group=self.group, period=None, academic_year="2025/2026")
            self._assign(other_year, group=self.group, period=None, academic_year="2024/2025", chair=self.faculty)
            ids = self._ids()
        self.assertIn(str(year_only.pk), ids)
        self.assertNotIn(str(other_year.pk), ids)

    def test_vacant_assignment_does_not_create_a_row(self):
        with bypass_rls():
            task, _created = TeachingTask.objects.get_or_create(
                organization=self.org, chair=self.chair, academic_year="2025/2026"
            )
            row = TeachingTaskRow.objects.create(organization=self.org, task=task, period=self.period, lecture_total=10)
            row.groups.set([self.group])
            TeacherAssignment.objects.create(
                organization=self.org, row=row, teacher=None, activity=Activity.LECTURE, hours=10
            )
            rows = _rows(self.coordinator, self.org, self.period)
        self.assertTrue(all(row["id"] and row["name"] for row in rows))

    def test_rows_are_unique_and_sorted_by_name(self):
        with bypass_rls():
            self._assign(self.teacher, group=self.group, period=self.period)
            self._offering(self.teacher, group=self.group_b)
            rows = _rows(self.coordinator, self.org, self.period)
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([row["name"] for row in rows], sorted(row["name"] for row in rows))

    def test_picker_is_a_handful_of_queries(self):
        with bypass_rls():
            self._assign(self._user("q1"), group=self.group, period=self.period)
            with CaptureQueriesContext(connection) as queries:
                _rows(self.coordinator, self.org, self.period)
        # əhatə (üzvlük/rol) sorğuları + rol id-ləri + TƏK istifadəçi sorğusu — N+1 yoxdur.
        self.assertLessEqual(len(queries), 12, [q["sql"][:80] for q in queries])


class HistoricalPeriodTest(PickerBase):
    def test_former_teacher_is_listed_for_the_old_period_only(self):
        gone = self._user("gone")
        with bypass_rls():
            self._offering(gone, period=self.past_period)
            gone.is_active = False
            gone.save(update_fields=["is_active"])
            Membership.objects.filter(user=gone, organization=self.org).update(is_active=False)
            old = self._ids(period=self.past_period)
            now = self._ids()
        self.assertIn(str(gone.pk), old)
        self.assertNotIn(str(gone.pk), now)

    def test_old_period_lists_only_people_who_taught_then(self):
        idle = self._user("idle2")
        taught = self._user("taught")
        with bypass_rls():
            self._assign(taught, group=self.group, period=self.past_period, academic_year="2023/2024")
            ids = self._ids(period=self.past_period)
        self.assertIn(str(taught.pk), ids)
        self.assertNotIn(str(idle.pk), ids)
        self.assertNotIn(str(self.teacher.pk), ids)  # cari dövrün müəllimi köhnə dövrdə dərs demirdi


class ScopeTest(PickerBase):
    def test_coordinator_does_not_see_out_of_scope_assignment_teachers(self):
        outsider = self._user("outsider")
        with bypass_rls():
            other_faculty = OrgUnit.objects.create(
                organization=self.org, name="Fakültə 2", slug="sedtp-fac2", unit_type=OrgUnitType.FACULTY
            )
            far_group = OrgUnit.objects.create(
                organization=self.org, parent=other_faculty, name="777X", slug="sedtp-far", unit_type=OrgUnitType.GROUP
            )
            self._assign(outsider, group=far_group, period=self.period)
            coordinator_ids = self._ids(self.coordinator)
            owner_ids = self._ids(self.owner)
        self.assertNotIn(str(outsider.pk), coordinator_ids)
        self.assertIn(str(outsider.pk), owner_ids)

    def test_actor_without_structure_access_gets_nothing(self):
        with bypass_rls():
            assignments = schedule_manage.scoped_assignments(self.student, self.org, period=self.period)
            self.assertFalse(assignments.exists())


class SectionTest(PickerBase):
    def test_blocked_teachers_deep_link_selects_nobody(self):
        with bypass_rls():
            self._offering(self.teacher)
        body = self._section(self.coordinator, sm_view="teacher", sm_teacher=str(self.teacher.pk)).content.decode()
        self.assertIn('data-teacher-id="%s"' % self.teacher.pk, body)
        with bypass_rls():
            User.objects.filter(pk=self.teacher.pk).update(is_active=False)
        body = self._section(self.coordinator, sm_view="teacher", sm_teacher=str(self.teacher.pk)).content.decode()
        self.assertNotIn('data-teacher-id="%s"' % self.teacher.pk, body)
