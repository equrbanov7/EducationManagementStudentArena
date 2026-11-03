"""«Cədvəldən kənar» işarəsi yapışıb qalmır (2026-11-03).

Dərs 21.10 (Çərşənbə) 11:50 «Data bərpası» ilə slotsuz açılıb → işarə yazılıb; cədvəl SONRA düzəlib. İndi:
slot yazılanda / dərs düzələndə / toplu dərcdən sonra / bir dəfəlik əmrlə cədvələ uyğun dərsin işarəsi
təmizlənir (tarixçə sətri ilə), uyğun olmayanınki qalır.
"""

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import gradebook_lessons, off_schedule_flags
from apps.registrar.models import Lesson, LessonMark, ScheduleSlot, Subject, WeekType
from apps.registrar.services import get_or_create_offering
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

WEDNESDAY = datetime.date(2026, 10, 21)
T1150, T1320 = datetime.time(11, 50), datetime.time(13, 20)


class OffScheduleFlagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("osf_admin", "osf_admin@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="OSF Univ",
                slug="osf-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.admin,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="OSF-1", slug="osf-g1", unit_type=OrgUnitType.GROUP
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
            cls.subject = Subject.objects.create(organization=cls.org, code="OSF101", name="Riyazi analiz")
            cls.offering = get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )

    def _lesson(self, *, date=WEDNESDAY, start=T1150, reason="Data bərpası — cədvəldə slot yox idi"):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=date,
                kind="seminar",
                start_time=start,
                end_time=T1320,
                off_schedule_reason=reason,
            )

    def _slot(self, *, weekday=3, start=T1150, **extra):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=weekday,
                start_time=start,
                end_time=T1320,
                week_type=WeekType.ALL,
                room="",
                **extra,
            )

    def _reason(self, lesson):
        return Lesson.objects.values_list("off_schedule_reason", flat=True).get(pk=lesson.pk)

    def _history(self):
        return AuditLog.objects.filter(
            resource_id=str(self.offering.pk), new_values__reason__startswith="off_schedule_reevaluated"
        )

    def test_slot_added_later_clears_the_flag_with_history(self):
        lesson = self._lesson()
        other_time = self._lesson(start=datetime.time(15, 15), reason="Kompensasiya dərsi")
        self._slot()
        self.assertEqual(self._reason(lesson), "")
        self.assertEqual(self._reason(other_time), "Kompensasiya dərsi")  # bu saata slot yoxdur — qalır
        entry = self._history().get()
        self.assertIn("Data bərpası", entry.changes[0]["old"])

    def test_wrong_day_and_parked_slot_keep_the_flag(self):
        lesson = self._lesson()
        self._slot(weekday=4)  # cümə axşamı
        self._slot(is_parked=True)
        self.assertNotEqual(self._reason(lesson), "")
        self.assertFalse(self._history().exists())

    def test_editing_a_slot_onto_the_lesson_time_clears_the_flag(self):
        lesson = self._lesson()
        slot = self._slot(start=datetime.time(10, 10))
        self.assertNotEqual(self._reason(lesson), "")
        slot.start_time = T1150
        with bypass_rls():
            slot.save(update_fields=["start_time", "updated_at"])
        self.assertEqual(self._reason(lesson), "")

    def test_lesson_update_onto_a_scheduled_time_clears_the_flag(self):
        self._slot()
        lesson = self._lesson(start=datetime.time(10, 10))
        self.assertNotEqual(self._reason(lesson), "")
        lesson.refresh_from_db()
        changed = gradebook_lessons.update_lesson(
            lesson=lesson, start_time=T1150, allow_past=True, allow_locked=True, by_user=self.admin
        )
        self.assertTrue(changed)
        self.assertEqual(self._reason(lesson), "")
        self.assertEqual(self._history().get().user, self.admin)

    def test_lesson_update_that_stays_off_schedule_keeps_the_flag(self):
        self._slot()
        lesson = self._lesson(start=datetime.time(10, 10))
        lesson.refresh_from_db()
        gradebook_lessons.update_lesson(lesson=lesson, topic="Limitlər", allow_past=True, allow_locked=True)
        self.assertNotEqual(self._reason(lesson), "")

    def test_bulk_created_slots_are_reevaluated_explicitly(self):
        lesson = self._lesson()
        with bypass_rls():
            ScheduleSlot.objects.bulk_create(
                [
                    ScheduleSlot(
                        organization=self.org,
                        offering=self.offering,
                        weekday=3,
                        start_time=T1150,
                        end_time=T1320,
                        week_type=WeekType.ALL,
                        room="",
                    )
                ]
            )
        self.assertNotEqual(self._reason(lesson), "")  # bulk_create siqnal göndərmir
        self.assertEqual(off_schedule_flags.reevaluate_offerings([self.offering.pk]), 1)
        self.assertEqual(self._reason(lesson), "")

    def test_command_dry_run_apply_and_idempotent_rerun(self):
        lesson = self._lesson()
        kept = self._lesson(start=datetime.time(15, 15), reason="Kompensasiya dərsi")
        self._slot(start=datetime.time(8, 30))
        # Köhnə data: slot əvvəldən var, işarə isə qalıb (siqnal hələ yox idi).
        self._slot()
        Lesson.objects.filter(pk=lesson.pk).update(off_schedule_reason="Data bərpası — köhnə işarə")
        marks_before = LessonMark.objects.count()

        def run(*extra):
            out = StringIO()
            call_command(
                "clear_stale_off_schedule_flags",
                "--org=osf-univ",
                f"--actor={self.admin.username}",
                "--period=Payız 2026/2027",
                *extra,
                stdout=out,
            )
            return out.getvalue()

        dry = run()
        self.assertIn("mode=dry_run", dry)
        self.assertIn("flagged=2 still_off_schedule=1 stale=1 cleared=1", dry)
        self.assertEqual(self._reason(lesson), "Data bərpası — köhnə işarə")  # dry-run geri qaytarılır

        applied = run("--apply")
        self.assertIn("stale=1 cleared=1", applied)
        self.assertEqual(self._reason(lesson), "")
        self.assertEqual(self._reason(kept), "Kompensasiya dərsi")
        self.assertEqual(LessonMark.objects.count(), marks_before)
        summary = AuditLog.objects.get(resource_id=off_schedule_flags.SOURCE_COMMAND)
        self.assertEqual(summary.new_values["lesson_ids"], [str(lesson.pk)])

        again = run("--apply", f"--offering={self.offering.pk}")
        self.assertIn("flagged=1 still_off_schedule=1 stale=0 cleared=0", again)
