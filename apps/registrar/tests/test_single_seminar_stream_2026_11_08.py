"""``single_seminar_stream_20261108`` — seminar bir axın: pay məhdudiyyəti + köhnə alt qrup bölgüsü açılır, undo."""

from __future__ import annotations

import datetime
import io
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.registrar.management.commands import single_seminar_stream_20261108 as stream
from apps.registrar.models import Enrollment, JournalShare, Lesson, LessonKind, SeminarGroup
from apps.registrar.tests.test_lab_groups_2026_11_06 import User, _LabWorld
from core.rls import bypass_rls


class SingleSeminarStreamTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.seminarist = User.objects.create_user("sss_sem", "sss_sem@x.test", "pw")
            self._member(self.seminarist, "teacher", ["grade.input"])
            self.share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.seminarist, kinds=["seminar"]
            )
            self.share.enrollments.add(self.e1)
            SeminarGroup.objects.create(organization=self.org, offering=self.offering, number=1, name="K1")
            SeminarGroup.objects.create(organization=self.org, offering=self.offering, number=2, name="K2")
            Enrollment.objects.filter(pk=self.e1.pk).update(seminar_group=1)
            Enrollment.objects.filter(pk=self.e2.pk).update(seminar_group=2)
        patch = mock.patch.object(stream, "PLAN", (str(self.offering.pk),))
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "single_seminar_stream_20261108", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            for item in line.split()[1:]:
                key, _, value = item.partition("=")
                counts[key] = value
        return counts

    def test_dry_run_then_apply_then_undo(self):
        counts = self._call()
        self.assertEqual(counts["shares_unrestricted"], "1")
        with bypass_rls():
            self.assertEqual(self.share.enrollments.count(), 1)  # dry-run geri qaytarılır
        counts = self._call("--apply")
        self.assertEqual(
            (counts["share_students_released"], counts["enrollment_seminar_groups_cleared"]),
            ("1", "2"),
        )
        self.assertEqual(counts["seminar_groups_deleted"], "2")
        with bypass_rls():
            self.assertFalse(self.share.enrollments.exists())
            self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, seminar_group__isnull=False).exists())
        self.assertEqual(self._call("--apply"), {"mode": "apply", "already_single": "1", **_zero()})
        counts = self._call("--undo", "--apply")
        self.assertEqual((counts["undo_groups_restored"], counts["undo_shares_restricted"]), ("2", "1"))
        with bypass_rls():
            self.assertEqual(list(self.share.enrollments.values_list("pk", flat=True)), [self.e1.pk])
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).seminar_group, 2)

    def test_tagged_seminar_lesson_blocks(self):
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today - datetime.timedelta(days=3),
                kind=LessonKind.SEMINAR,
                seminar_group=1,
            )
        self.assertEqual(self._call("--apply"), {"mode": "apply", "blocked_tagged_lessons": "1"})


def _zero():
    return {"enrollment_seminar_groups_cleared": "0", "seminar_groups_deleted": "0"}
