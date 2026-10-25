"""Sahib 2026-10-25: «qb» yazılanda tələbəyə bildiriş (və telefona push) — bir DƏRS üçün bir dəfə.

* q/b yazılır → tələbəyə bir bildiriş (dərsin tarixi ilə), ``metadata.absent_lessons``-da dərs id-si;
* eyni dərsdə q/b → i/e → q/b (düzəliş) → ikinci bildiriş YOXDUR;
* bir yazıda iki dərsin q/b-si → tələbə başına TƏK bildiriş;
* mətn oxuyanın dilində (LText deskriptoru).
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.notifications.i18n import localize_notification
from apps.notifications.models import InAppNotification
from apps.registrar import gradebook
from apps.registrar.models import AttendanceStatus
from apps.registrar.tests.test_audit_2026_09_28_journal import _JournalFixture
from core.rls import bypass_rls

T1015 = datetime.time(10, 15)
T1145 = datetime.time(11, 45)


class QbNotificationOnceTests(_JournalFixture):
    def _save(self, *cells):
        entries = [
            {"lesson_id": str(lesson.pk), "enrollment_id": str(self.enrollment.pk), "status": status, "score": ""}
            for lesson, status in cells
        ]
        with self.captureOnCommitCallbacks(execute=True):
            with bypass_rls():
                gradebook.save_marks(offering=self.offering, entries=entries, by_user=self.teacher)

    def _notifications(self):
        with bypass_rls():
            return list(InAppNotification.objects.filter(recipient=self.student).order_by("pk"))

    def test_absent_is_notified_once_per_lesson(self):
        with bypass_rls():
            lesson = self._lesson()
        self._save((lesson, AttendanceStatus.ABSENT))
        rows = self._notifications()
        self.assertEqual(len(rows), 1)
        today = timezone.localdate().strftime("%d.%m.%Y")
        self.assertEqual(rows[0].message, f"Qayıb (q/b) qeyd edildi: {today}")
        self.assertEqual(rows[0].metadata["absent_lessons"], [str(lesson.pk)])
        self.assertEqual(
            localize_notification(rows[0], "ru").message.split(":")[0],
            "Пропуск (q/b) отмечен",
        )

        # Düzəliş: i/e → yenidən q/b — eyni dərs üçün ikinci bildiriş yoxdur.
        self._save((lesson, AttendanceStatus.PRESENT))
        self._save((lesson, AttendanceStatus.ABSENT))
        self.assertEqual(len(self._notifications()), 1)

    def test_bulk_save_is_one_notification_per_student(self):
        with bypass_rls():
            first = self._lesson()
            second = self._lesson(start=T1015, end=T1145)
        self._save((first, AttendanceStatus.ABSENT), (second, AttendanceStatus.ABSENT))
        rows = self._notifications()
        self.assertEqual(len(rows), 1)
        self.assertEqual(sorted(rows[0].metadata["absent_lessons"]), sorted([str(first.pk), str(second.pk)]))
        # Eyni tarixli iki dərs — sətir bir dəfə (təkrar sətir atılır).
        self.assertEqual(rows[0].message.count("Qayıb (q/b) qeyd edildi"), 1)
