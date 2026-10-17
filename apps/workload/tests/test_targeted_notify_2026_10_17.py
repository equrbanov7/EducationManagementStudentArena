"""Sahib 2026-10-17 «Yeni müəllimlərə bildiriş getsin»: əvvəl bölünmüş sənədin yenidən təsdiqi.

``loads_before`` (``teacher_loads``) ilə yenidən təsdiq kafedranın bütün müəllimlərinə təkrar «Dərs yükü
təyin edildi» GÖNDƏRMİR — yalnız bölgüsü yeni yaranan / dəyişən müəllimə bir dəfə; ilk təsdiq hamıya.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.notifications.models import InAppNotification
from apps.workload.constants import Activity, AmendmentReason, AmendmentTarget, TaskStatus
from apps.workload.services import assign_amended, confirm_distribution, open_amendment, save_row_amended
from apps.workload.services.distribution import changed_teacher_ids, teacher_loads
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member
from .test_row_edit_amend_2026_10_15 import _DistributedTaskMixin

User = get_user_model()
AMEND = {"reason": "official", "note": "Cədvəldən yeni sətir"}


def _notified(user) -> int:
    return InAppNotification.objects.filter(recipient=user, metadata__event="workload_assigned").count()


class TargetedReconfirmNotifyTest(_DistributedTaskMixin, TestCase):
    code = "WTN"

    def setUp(self):
        super().setUp()
        self.newcomer = User.objects.create_user("wtn_new", "wtn_new@x.test", "pw")
        activate_member(
            self.org,
            self.newcomer,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.assertEqual(_notified(self.teacher), 1)  # ilk təsdiq — hamıya

    def _add_row_for_newcomer(self):
        row = save_row_amended(
            task=self.task, actor=self.actor, data={"subject_text": "Yeni fənn", "lecture_total": 30}, amend=AMEND
        )
        assign_amended(
            row=row, actor=self.actor, amend=AMEND, activity=Activity.LECTURE, teacher_id=self.newcomer.pk, hours=30
        )

    def test_new_teacher_gets_one_notification_existing_none(self):
        before = teacher_loads(self.task)
        self._add_row_for_newcomer()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        self.assertEqual(changed_teacher_ids(self.task, before), {self.newcomer.pk})

        result = confirm_distribution(task=self.task, actor=self.actor, loads_before=before)
        self.assertEqual(result["notified"], 1)
        self.assertEqual(_notified(self.newcomer), 1)
        self.assertEqual(_notified(self.teacher), 1)
        note = InAppNotification.objects.get(recipient=self.newcomer, metadata__event="workload_assigned")
        self.assertIn("Dərs yükü təyin edildi", note.title)
        self.assertIn("30 saat", note.title)

    def test_reconfirm_without_changes_sends_nothing(self):
        before = teacher_loads(self.task)
        open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.OFFICIAL,
            note="Dəyişiklik yoxdur",
        )
        result = confirm_distribution(task=self.task, actor=self.actor, loads_before=before)
        self.assertEqual(result["notified"], 0)
        self.assertEqual(_notified(self.teacher), 1)

    def test_without_snapshot_reconfirm_keeps_notify_all(self):
        # UI yolu (``loads_before`` yoxdur) — köhnə davranış: hamıya.
        self._add_row_for_newcomer()
        result = confirm_distribution(task=self.task, actor=self.actor)
        self.assertEqual(result["notified"], 2)
        self.assertEqual(_notified(self.teacher), 2)


class FixRowHoursTargetedNotifyTest(_DistributedTaskMixin, TestCase):
    code = "WTF"

    def setUp(self):
        super().setUp()
        User.objects.create_superuser("wtf_root", "wtf_root@x.test", "pw")
        self.stack["group"].name = "631/5K"
        self.stack["group"].save(update_fields=["name"])

    def _call(self):
        out = StringIO()
        call_command(
            "fix_task_row_hours",
            "--org", self.org.slug, "--year", YEAR, "--chair", self.stack["chair"].name,
            "--group", "631/5K", "--subject", self.stack["subject"].name, "--activity", "lab", "--hours", "0",
            "--reason", "Lab xanasına cəm yazılıb", "--actor", "wtf_root", "--apply", stdout=out,
        )  # fmt: skip
        return out.getvalue()

    def test_teacher_whose_hours_changed_is_notified_once_and_rerun_sends_nothing(self):
        self.assertEqual(_notified(self.teacher), 1)
        self.assertIn("reconfirmed=1", self._call())
        self.assertEqual(_notified(self.teacher), 2)
        latest = InAppNotification.objects.filter(recipient=self.teacher).order_by("-created_at").first()
        self.assertIn("45 saat", latest.title)
        self.assertIn("unchanged=1", self._call())
        self.assertEqual(_notified(self.teacher), 2)
        self.assertEqual(_notified(self.head), 0)
