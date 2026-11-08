"""Sahib 2026-11-08 (135 TSPX): «əvvəlki jurnal» surət sətri — hər xanası hədəfin eyni dərsində varsa bağ açılır."""

import datetime
import io

from django.core.management import call_command

from apps.organizations.models import AcademicPeriod
from apps.registrar import guest_merge
from apps.registrar.models import Enrollment, Lesson
from apps.registrar.tests import test_enrollment_history_carry as carry_tests
from core.rls import bypass_rls

T = datetime.time(10, 10)


class DuplicatePredecessorUnlinkTests(carry_tests.ExactHistoryCarryTests):
    def _call(self, *extra):
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])
        AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=True, is_active=True)
        out = io.StringIO()
        call_command(
            "recompute_carried_absences_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line.split(": ", 1)[1].split())
        return counts

    def _timed(self, row, index):
        mark = self.mark(row, index)
        Lesson.objects.filter(pk=mark.lesson_id).update(start_time=T)
        return mark

    def test_pure_copy_is_unlinked_and_undo_relinks(self):
        source, target = self.transition()
        for index in (0, 1):
            self._timed(source, index)
            self._timed(target, index)
        self.assertEqual(guest_merge.carried_absence_hours(target), 4)
        self.assertEqual(self._call()["predecessors_unlinked"], "1")  # dry-run
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=source.pk).superseded_by_id, target.pk)
        counts = self._call("--apply")
        self.assertEqual(counts["duplicate_absence_hours_removed"], "4")
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 4)
        self.assertEqual(self._call("--apply", "--undo")["undo_relinked"], "1")
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 8)

    def test_partly_unique_predecessor_stays_linked(self):
        source, target = self.transition()
        self._timed(source, 0)
        self._timed(target, 0)
        self._timed(source, 1)  # yalnız əvvəlki jurnalda
        self.assertNotIn("predecessors_unlinked", self._call("--apply"))
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=source.pk).superseded_by_id, target.pk)
