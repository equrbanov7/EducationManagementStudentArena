"""Sahib 2026-11-12: «Bölgünü təsdiqlə» natamam sətirləri göstərir; «Aydındır» → qalan saat «Vakant», təsdiq.

«Bunu elə et ki, kimsə təyin olunmasa, mən bölgünü təsdiqləyəndə aydın info versin və "aydındır" deyəndən sonra
təsdiqlənsin, onda vakantda qalsın.» Bayraqsız sorğu əvvəlki kimi rədd olunur (indi 409 + sətir siyahısı),
``fill_vacant=1`` qalan saatları «Vakant» yazıb təsdiqləyir; artıq bölgü sərt maneədir.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.registrar.models import CourseOffering
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from apps.workload.services import assign_teacher, confirm_distribution, open_amendment, resolve_actor
from apps.workload.services.confirm_vacant import VACANT_NOTE
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class ConfirmWithVacantTest(TestCase):
    code = "CVA"

    def setUp(self):
        self.org = make_org(f"wl-{self.code.lower()}")
        self.stack = make_structure(self.org, code=self.code)
        self.head = User.objects.create_user(f"{self.code}_head", f"{self.code}_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user(f"{self.code}_teacher", f"{self.code}_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.head)
        # Mühazirə 30 (müəllimdə), seminar 15 — heç kimə bölünməyib.
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=30)
        self.client.force_login(self.head)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _confirm(self, **extra):
        return self.client.post(
            reverse("workload:confirm"),
            data=json.dumps({"task_id": str(self.task.pk), **extra}),
            content_type="application/json",
        )

    def _instructors(self):
        return dict(CourseOffering.objects.filter(organization=self.org).values_list("pk", "instructor_id"))

    def test_without_flag_returns_structured_list(self):
        response = self._confirm()
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["error"], "workload.distribution_incomplete")
        rows = body["readiness"]["incomplete_rows"]
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.assertEqual(item["row_id"], str(self.row.pk))
        self.assertEqual(item["subject"], self.stack["subject"].name)
        self.assertEqual(item["groups"], self.stack["group"].name)
        self.assertEqual(item["specialty"], self.stack["specialty"].name)
        self.assertFalse(item["is_over"])
        self.assertEqual([(gap["activity"], gap["remaining"]) for gap in item["gaps"]], [(str(Activity.SEMINAR), 15)])
        self.assertEqual(body["readiness"]["unassigned_hours"], 15)
        self.task.refresh_from_db()
        self.assertNotEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row, teacher__isnull=True).exists())

    def test_flag_fills_vacant_and_confirms_without_journal_moves_or_vacant_notifications(self):
        before = self._instructors()
        self.assertTrue(before)
        response = self._confirm(fill_vacant="1")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], TaskStatus.DISTRIBUTED)
        self.assertEqual(body["vacant_filled"], {"rows": 1, "hours": 15})

        vacant = TeacherAssignment.objects.get(row=self.row, teacher__isnull=True)
        self.assertEqual((vacant.activity, vacant.hours, vacant.note), (str(Activity.SEMINAR), 15, VACANT_NOTE))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(self._instructors(), before)  # jurnal müəllimi dəyişmədi
        self.assertEqual(set(before.values()), {self.teacher.pk})
        # Bildiriş yalnız real müəllimə (təsdiq qaydası), «Vakant»ın alıcısı yoxdur.
        recipients = set(
            InAppNotification.objects.filter(metadata__event="workload_assigned").values_list("recipient_id", flat=True)
        )
        self.assertEqual(recipients, {self.teacher.pk})
        audit = AuditLog.objects.get(organization=self.org, reason="workload.confirm_vacant_filled")
        filled = audit.new_values["filled"]
        self.assertEqual(
            [(e["row_id"], e["activity"], e["hours"]) for e in filled], [(str(self.row.pk), "seminar", 15)]
        )

    def test_over_assigned_is_hard_blocker_even_with_flag(self):
        # Artıq bölgü (DB qoruyucusu yazıda tutur, amma köhnə/idxal datasında cəm sonradan azala bilər).
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=self.teacher.pk, hours=15)
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(seminar_total=10, seminar_plan=10)
        for extra in ({}, {"fill_vacant": "1"}):
            response = self._confirm(**extra)
            self.assertEqual(response.status_code, 409, response.content)
            body = response.json()
            self.assertEqual(body["error"], "workload.distribution_over_assigned")
            self.assertIn(self.stack["subject"].name, body["message"])
            self.assertTrue(body["readiness"]["incomplete_rows"][0]["is_over"])
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row, teacher__isnull=True).exists())
        self.task.refresh_from_db()
        self.assertNotEqual(self.task.status, TaskStatus.DISTRIBUTED)

    def test_amended_task_opens_system_amendment_for_vacant_rows(self):
        # Bölgü tam təsdiqlənir, sonra başqa sətir üçün düzəliş açılır və yeni natamam sətir əlavə olunur.
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=self.teacher.pk, hours=15)
        confirm_distribution(task=self.task, actor=self.actor, notify=False)
        self.task.refresh_from_db()
        open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind="row",
            target_id=self.row.pk,
            reason="correction",
            note="Saat düzəlişi",
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        other = make_row(self.task, self.stack, lecture_total=0, seminar_total=0, lab_total=30)
        before_amendments = set(WorkloadAmendment.objects.filter(task=self.task).values_list("pk", flat=True))

        response = self._confirm(fill_vacant="1")
        self.assertEqual(response.status_code, 200, response.content)
        vacant = TeacherAssignment.objects.get(row=other, teacher__isnull=True)
        self.assertEqual((vacant.activity, vacant.hours), (str(Activity.LAB), 30))
        new = WorkloadAmendment.objects.filter(task=self.task).exclude(pk__in=before_amendments).get()
        self.assertEqual((new.target_id, new.reason, new.note), (other.pk, "other", VACANT_NOTE))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)

    def test_complete_distribution_confirms_as_before(self):
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=None, hours=15)
        response = self._confirm()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["vacant_filled"], {"rows": 0, "hours": 0})
