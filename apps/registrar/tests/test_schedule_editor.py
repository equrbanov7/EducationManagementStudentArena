"""Cədvəl REDAKTORU — matris, konflikt mühərriki, park, tövsiyə, yumşaq silmə.

Nəyi qoruyur
------------
Sahibin 2026-09-09 tələbləri:

* «Cədvəl olmasa da burada həmişə, boş da olsa, cədvəl görünsün» — matris
  sətirləri slotlardan YOX, nömrələnmiş dərs saatlarından qurulur;
* «xanaya klik edərək … müəllim seçilsin, fənn seçilsin …» — hüceyrə dialoqu
  mövcud ``CourseOffering``-ə bağlanır, paralel model YARADILMIR;
* «müəllimin filan saatda filan qrupa dərsi var» — konflikt SERVERDƏ tapılır və
  qrup/fənn/vaxt adı ilə strukturlu qaytarılır (üst/alt həftə nəzərə alınır);
* «digər qrupdan müəllimin dərsi … haradasa qalsın ki onu başqa yerə dəyişmək
  mümkün olsun» — məcburi dəyişiklikdə toqquşan slot PARKLANIR, silinmir;
* «hara boşdursa orada ola bilər» — tövsiyə yalnız HƏM müəllimin, HƏM qrupun
  boş olduğu hüceyrələri qaytarır;
* layihə qaydası: heç nə sərt silinmir (yumşaq silmə).
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_conflicts, schedule_editor
from apps.registrar import schedule_editor_actions as editor
from apps.registrar import schedule_grid
from apps.registrar import schedule_manage_actions as base
from apps.registrar import services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    ScheduleSlot,
    Subject,
    WeekType,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ScheduleEditorBase(TestCase):
    """İki qrup + iki müəllim: konflikt və park ssenariləri üçün minimal ağac."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sed_owner", "sed_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SED Univ",
                slug="sed-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="sed-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas",
                slug="sed-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, parent=cls.speciality, name="231A", slug="sed-g1", unit_type=OrgUnitType.GROUP
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, parent=cls.speciality, name="231B", slug="sed-g2", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=datetime.date.today() - datetime.timedelta(days=10),
                end_date=datetime.date.today() + datetime.timedelta(days=100),
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.subject_b = Subject.objects.create(organization=cls.org, code="CS202", name="Alqoritmlər")

            cls.teacher = User.objects.create_user("sed_teacher", "sed_t@qku.edu.az", "pw")
            cls.teacher_b = User.objects.create_user("sed_teacher_b", "sed_tb@qku.edu.az", "pw")
            cls.coordinator = User.objects.create_user("sed_coord", "sed_c@qku.edu.az", "pw")
            for user, role in (
                (cls.teacher, "teacher"),
                (cls.teacher_b, "teacher"),
            ):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
            Membership.objects.create(
                user=cls.coordinator,
                organization=cls.org,
                role=cls.org.roles.get(name="program_coordinator"),
                scope_unit=cls.speciality,
                is_primary=True,
                is_active=True,
            )

            cls.program = Program.objects.create(organization=cls.org, code="SED-CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            for index, subject in enumerate((cls.subject, cls.subject_b), start=1):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=index
                )

            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.offering_b = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group_b
            )
            cls.offering_b.instructor = cls.teacher
            cls.offering_b.save(update_fields=["instructor"])

    def _payload(self, **overrides):
        data = {
            "subject_id": str(self.subject.id),
            "instructor_id": str(self.teacher.id),
            "weekday": "1",
            "time_slot": "10:10|11:40",
            "week_type": WeekType.ALL,
            "slot_kind": "lecture",
            "room": "",
        }
        data.update(overrides)
        return data

    def _save(self, **overrides):
        return editor.save_cell(
            actor=self.coordinator,
            organization=self.org,
            group=self.group,
            period=self.period,
            data=self._payload(**overrides),
        )

    def _slot(self, *, offering, weekday=1, start="10:10", end="11:40", week_type=WeekType.ALL, room=""):
        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=offering,
            weekday=weekday,
            start_time=datetime.time.fromisoformat(start),
            end_time=datetime.time.fromisoformat(end),
            week_type=week_type,
            room=room,
        )


class AlwaysVisibleGridTest(ScheduleEditorBase):
    """«Cədvəl olmasa da … boş da olsa cədvəl görünsün» (sahib, 2026-09-09)."""

    def test_matrix_is_fully_built_with_zero_slots(self):
        with bypass_rls():
            matrix = schedule_grid.build_matrix(slots=[], organization=self.org)
        self.assertEqual(len(matrix["day_headers"]), 6)
        self.assertEqual(len(matrix["rows"]), len(schedule_service.STANDARD_LESSON_TIMES))
        self.assertFalse(matrix["has_slots"])
        for row in matrix["rows"]:
            self.assertEqual(len(row["cells"]), 6)
            self.assertTrue(all(cell["is_empty"] for cell in row["cells"]))

    def test_lesson_hours_come_from_tenant_settings_when_configured(self):
        with bypass_rls():
            self.org.settings = {"lesson_times": [["09:00", "10:20"], ["10:30", "11:50"]]}
            rows = schedule_grid.lesson_periods(self.org)
        self.assertEqual([row["key"] for row in rows], ["09:00|10:20", "10:30|11:50"])
        self.assertEqual([row["no"] for row in rows], [1, 2])

    def test_slot_outside_the_bell_schedule_still_shows_in_an_extra_row(self):
        with bypass_rls():
            slot = self._slot(offering=self.offering, start="07:15", end="08:00")
            matrix = schedule_grid.build_matrix(slots=[slot], organization=self.org)
        self.assertEqual(len(matrix["extra_rows"]), 1)
        self.assertEqual(matrix["extra_rows"][0]["key"], "07:15|08:00")


class CellCreateTest(ScheduleEditorBase):
    """Boş xanadan slot yaratmaq — mövcud açılışa bağlanır, yeni model YOX."""

    def test_cell_dialog_creates_a_slot_on_the_existing_offering(self):
        with bypass_rls():
            result = self._save()
            slot = ScheduleSlot.objects.get(pk=result["slot"]["id"])
        self.assertEqual(slot.offering_id, self.offering.id)
        self.assertEqual(slot.weekday, 1)
        self.assertEqual(slot.start_time, datetime.time(10, 10))
        self.assertFalse(slot.is_parked)

    def test_missing_offering_is_created_for_a_curriculum_subject(self):
        with bypass_rls():
            result = editor.save_cell(
                actor=self.coordinator,
                organization=self.org,
                group=self.group,
                period=self.period,
                data=self._payload(subject_id=str(self.subject_b.id), instructor_id=str(self.teacher_b.id)),
            )
            slot = ScheduleSlot.objects.get(pk=result["slot"]["id"])
        self.assertEqual(slot.offering.subject_id, self.subject_b.id)
        self.assertEqual(slot.offering.instructor_id, self.teacher_b.id)

    def test_changing_the_instructor_of_a_bound_offering_is_refused(self):
        with bypass_rls():
            with self.assertRaises(schedule_editor.CellError) as ctx:
                self._save(instructor_id=str(self.teacher_b.id))
        self.assertEqual(ctx.exception.code, "instructor_locked")
        self.assertEqual(ctx.exception.status, 409)

    def test_allowed_subjects_are_limited_to_the_group_plan(self):
        with bypass_rls():
            from apps.registrar.models import AcademicStatus, StudentAcademicRecord

            student = User.objects.create_user("sed_student_x", "sed_sx@qku.edu.az", "pw")
            Membership.objects.create(
                user=student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                scope_unit=self.group,
                is_primary=True,
                is_active=True,
            )
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2025,
                status=AcademicStatus.ENROLLED,
            )
            other = Subject.objects.create(organization=self.org, code="ZZ999", name="Plandan kənar")
            rows = schedule_editor.allowed_subjects(organization=self.org, group=self.group, period=self.period)
        codes = {row["code"] for row in rows}
        self.assertIn("CS101", codes)
        self.assertIn("CS202", codes)
        self.assertNotIn(other.code, codes)


class ConflictEngineTest(ScheduleEditorBase):
    """Müəllim / qrup / otaq toqquşmaları — üst/alt həftə və vaxt kəsişməsi."""

    def _detect(self, **kwargs):
        params = {
            "organization": self.org,
            "weekday": 1,
            "start_time": datetime.time(10, 10),
            "end_time": datetime.time(11, 40),
            "week_type": WeekType.ALL,
            "room": "",
            "group_id": self.group.id,
            "instructor_id": self.teacher.id,
        }
        params.update(kwargs)
        return schedule_conflicts.detect(**params)

    def test_teacher_conflict_names_the_other_group_and_time(self):
        with bypass_rls():
            self._slot(offering=self.offering_b)
            found = self._detect()
        kinds = [row["kind"] for row in found]
        self.assertIn(schedule_conflicts.KIND_TEACHER, kinds)
        message = next(row["message"] for row in found if row["kind"] == schedule_conflicts.KIND_TEACHER)
        self.assertIn("231B", message)
        self.assertIn("10:10", message)

    def test_group_conflict_is_reported(self):
        with bypass_rls():
            other = services.get_or_create_offering(
                organization=self.org, subject=self.subject_b, period=self.period, group=self.group
            )
            other.instructor = self.teacher_b
            other.save(update_fields=["instructor"])
            self._slot(offering=other)
            found = self._detect()
        self.assertEqual([row["kind"] for row in found], [schedule_conflicts.KIND_GROUP])

    def test_room_conflict_is_reported(self):
        with bypass_rls():
            other = services.get_or_create_offering(
                organization=self.org, subject=self.subject_b, period=self.period, group=self.group_b
            )
            other.instructor = self.teacher_b
            other.save(update_fields=["instructor"])
            self._slot(offering=other, room="A-201")
            found = self._detect(room="a-201", instructor_id=self.teacher_b.id and None)
        self.assertEqual([row["kind"] for row in found], [schedule_conflicts.KIND_ROOM])

    def test_partial_time_overlap_counts_even_with_different_start(self):
        with bypass_rls():
            self._slot(offering=self.offering_b, start="10:40", end="12:00")
            found = self._detect()
        self.assertTrue(found, "vaxt aralığı kəsişir — toqquşma tapılmalıdır")

    def test_odd_and_even_weeks_do_not_clash(self):
        with bypass_rls():
            self._slot(offering=self.offering_b, week_type=WeekType.ODD)
            found = self._detect(week_type=WeekType.EVEN)
        self.assertEqual(found, [])

    def test_all_week_clashes_with_both_parities(self):
        with bypass_rls():
            self._slot(offering=self.offering_b, week_type=WeekType.ODD)
            odd_clash = self._detect(week_type=WeekType.ALL)
            found_even = schedule_conflicts.detect(
                organization=self.org,
                weekday=1,
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                week_type=WeekType.EVEN,
                room="",
                group_id=self.group.id,
                instructor_id=self.teacher.id,
            )
        self.assertTrue(odd_clash)
        self.assertEqual(found_even, [])

    def test_parked_slot_frees_its_cell(self):
        with bypass_rls():
            other = self._slot(offering=self.offering_b)
            other.is_parked = True
            other.save(update_fields=["is_parked"])
            found = self._detect()
        self.assertEqual(found, [])

    def test_save_without_force_is_refused_and_carries_the_payload(self):
        with bypass_rls():
            self._slot(offering=self.offering_b)
            with self.assertRaises(schedule_editor.CellError) as ctx:
                self._save()
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertEqual(ctx.exception.status, 409)
        self.assertTrue(ctx.exception.extra["conflicts"])
        self.assertIn("suggestions", ctx.exception.extra)


class ForcedMoveParkingTest(ScheduleEditorBase):
    """Məcburi dəyişiklik — toqquşan slot SİLİNMİR, parklanır və görünür."""

    def test_forced_save_parks_the_other_slot_instead_of_deleting_it(self):
        with bypass_rls():
            other = self._slot(offering=self.offering_b)
            result = self._save(force=True, reason="Auditoriya təmiri səbəbindən məcburi köçürmə")
            other.refresh_from_db()
            parked = editor.parked_rows(organization=self.org, period=self.period)
        self.assertTrue(other.is_parked)
        self.assertFalse(other.is_deleted)
        self.assertEqual(other.park_reason, "Auditoriya təmiri səbəbindən məcburi köçürmə")
        self.assertEqual([row["id"] for row in result["parked"]], [str(other.pk)])
        self.assertIn(str(other.pk), [row["id"] for row in parked])

    def test_parked_list_is_limited_to_the_actor_scope(self):
        with bypass_rls():
            outside_group = OrgUnit.objects.create(
                organization=self.org, name="Kənar B", slug="sed-out-3", unit_type=OrgUnitType.GROUP
            )
            outside = services.get_or_create_offering(
                organization=self.org, subject=self.subject_b, period=self.period, group=outside_group
            )
            slot = self._slot(offering=outside, weekday=5)
            slot.is_parked = True
            slot.save(update_fields=["is_parked"])
            scoped = editor.parked_rows(organization=self.org, period=self.period, actor=self.coordinator)
            unscoped = editor.parked_rows(organization=self.org, period=self.period)
        self.assertEqual(scoped, [])
        self.assertEqual([row["id"] for row in unscoped], [str(slot.pk)])

    def test_forced_save_requires_a_reason(self):
        with bypass_rls():
            self._slot(offering=self.offering_b)
            with self.assertRaises(schedule_editor.CellError) as ctx:
                self._save(force=True, reason="qısa")
        self.assertEqual(ctx.exception.code, "reason_required")

    def test_parked_slot_can_be_placed_again(self):
        with bypass_rls():
            other = self._slot(offering=self.offering_b)
            self._save(force=True, reason="Məcburi dəyişiklik — dekanlığın sərəncamı")
            other.refresh_from_db()
            editor.place_parked(
                actor=self.coordinator,
                organization=self.org,
                slot=other,
                data={"weekday": 3, "time_slot": "13:35|15:05"},
            )
            other.refresh_from_db()
        self.assertFalse(other.is_parked)
        self.assertEqual(other.weekday, 3)
        self.assertEqual(other.start_time, datetime.time(13, 35))

    def test_forced_move_outside_the_actor_scope_is_refused(self):
        with bypass_rls():
            outside_group = OrgUnit.objects.create(
                organization=self.org, name="Kənar", slug="sed-out", unit_type=OrgUnitType.GROUP
            )
            outside = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=outside_group
            )
            outside.instructor = self.teacher
            outside.save(update_fields=["instructor"])
            blocker = self._slot(offering=outside)
            with self.assertRaises(schedule_editor.CellError) as ctx:
                self._save(force=True, reason="Səlahiyyətdən kənar məcburi dəyişiklik cəhdi")
            blocker.refresh_from_db()
        self.assertEqual(ctx.exception.status, 403)
        self.assertFalse(blocker.is_parked)


class SuggestionTest(ScheduleEditorBase):
    """«Hara boşdursa» — həm müəllim, həm qrup boş olan hüceyrələr."""

    def test_busy_cells_are_excluded(self):
        with bypass_rls():
            self._slot(offering=self.offering_b, weekday=1, start="10:10", end="11:40")
            rows = schedule_conflicts.suggest(
                organization=self.org, group_id=self.group.id, instructor_id=self.teacher.id, limit=100
            )
        busy = [row for row in rows if row["weekday"] == 1 and row["time_slot"] == "10:10|11:40"]
        self.assertEqual(busy, [])
        self.assertTrue(rows)

    def test_shift_filter_only_returns_that_shift(self):
        with bypass_rls():
            rows = schedule_conflicts.suggest(
                organization=self.org,
                group_id=self.group.id,
                instructor_id=self.teacher.id,
                shift=schedule_grid.SHIFT_AFTERNOON,
                limit=100,
            )
        self.assertTrue(rows)
        self.assertTrue(all(row["shift"] == schedule_grid.SHIFT_AFTERNOON for row in rows))

    def test_days_where_the_group_already_studies_rank_first(self):
        with bypass_rls():
            self._slot(offering=self.offering, weekday=2, start="08:30", end="10:00")
            rows = schedule_conflicts.suggest(
                organization=self.org, group_id=self.group.id, instructor_id=self.teacher.id, limit=3
            )
        self.assertEqual(rows[0]["weekday"], 2)


class SoftDeleteTest(ScheduleEditorBase):
    """Layihə qaydası: slot bazadan SİLİNMİR (yalnız `is_deleted`)."""

    def test_delete_is_soft_and_the_row_survives(self):
        with bypass_rls():
            slot = self._slot(offering=self.offering)
            base.delete_slot(actor=self.coordinator, organization=self.org, slot=slot, request=None)
            self.assertFalse(ScheduleSlot.objects.filter(pk=slot.pk).exists())
            row = ScheduleSlot.all_objects.get(pk=slot.pk)
        self.assertTrue(row.is_deleted)
        self.assertIsNotNone(row.deleted_at)

    def test_deleted_slots_leave_the_group_schedule(self):
        with bypass_rls():
            slot = self._slot(offering=self.offering)
            base.delete_slot(actor=self.coordinator, organization=self.org, slot=slot, request=None)
            rows = schedule_service.get_group_schedule(organization=self.org, group=self.group, period=self.period)
        self.assertEqual(rows, [])


class DryCheckTest(ScheduleEditorBase):
    """«Konflikt yoxla» quru icradır — bazaya HEÇ NƏ yazmır."""

    def test_check_does_not_create_the_offering(self):
        with bypass_rls():
            before = CourseOffering.objects.filter(organization=self.org).count()
            offering, created, assigned = schedule_editor.resolve_offering(
                actor=self.coordinator,
                organization=self.org,
                group=self.group_b,
                period=self.period,
                subject=self.subject_b,
                instructor=self.teacher_b,
                create=False,
            )
            cleaned, errors = schedule_editor.parse_cell(
                {"weekday": "2", "time_slot": "08:30|10:00", "week_type": WeekType.ALL, "slot_kind": "lecture"},
                organization=self.org,
            )
            verdict = schedule_editor.check_cell(organization=self.org, offering=offering, cleaned=cleaned)
            after = CourseOffering.objects.filter(organization=self.org).count()
        self.assertEqual(errors, {})
        self.assertTrue(offering._state.adding, "quru yoxlamada açılış YADDA SAXLANMAMALIDIR")
        self.assertFalse(created or assigned)
        self.assertTrue(verdict["ok"])
        self.assertEqual(before, after)

    def test_actor_outside_the_scope_cannot_create_an_offering(self):
        with bypass_rls():
            outside_group = OrgUnit.objects.create(
                organization=self.org, name="Kənar qrup", slug="sed-out-2", unit_type=OrgUnitType.GROUP
            )
            before = CourseOffering.objects.filter(organization=self.org).count()
            with self.assertRaises(schedule_editor.CellError) as ctx:
                editor.save_cell(
                    actor=self.coordinator,
                    organization=self.org,
                    group=outside_group,
                    period=self.period,
                    data=self._payload(subject_id=str(self.subject_b.id)),
                )
            after = CourseOffering.objects.filter(organization=self.org).count()
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(before, after)
