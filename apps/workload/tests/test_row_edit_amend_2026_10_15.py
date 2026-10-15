"""2026-10-15 (sahib): RİM və kafedra müdiri TƏSDİQLƏNMİŞ yükü redaktə edir — rəsmi düzəliş axını ilə.

«631/5K … 45 saat toplam … bunları edit etmək olmur. RİM ya da kafedra müdiri edit edə bilsin, çıxarda,
əlavə edə». Əvvəl ``distributed`` sənəddə hər yazı ``task_not_editable`` / ``task_not_assignable`` verirdi
və düzəliş dialoqunu açan heç nə yox idi. İndi endpoint-lər səbəbsiz yazıya ``amendment_required`` (409)
qaytarır, səbəb + qeydlə isə düzəliş açıb dəyişikliyi edir; müəllim yalnız oxuyur.
"""

from __future__ import annotations

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from apps.registrar.models import CourseOffering
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from apps.workload.services import (
    assign_amended,
    assign_teacher,
    confirm_distribution,
    resolve_actor,
    save_row_amended,
)
from apps.workload.services.my_workload_lines import group_workload_lines
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
AMEND = {"amend_reason": "correction", "amend_note": "Kitabçada laboratoriya xanasına cəm yazılıb"}


class _DistributedTaskMixin:
    """Kafedra: 30 mühazirə + 15 seminar + 45 (SƏHV) laboratoriya, hamısı bir müəllimdə, bölgü təsdiqlənib."""

    code = "WRE"

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
            permissions=TEACHER_PERMS + ["workload.object"],
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15, lab_total=45)
        for activity, hours in ((Activity.LECTURE, 30), (Activity.SEMINAR, 15), (Activity.LAB, 45)):
            assign_teacher(row=self.row, actor=self.actor, activity=activity, teacher_id=self.teacher.pk, hours=hours)
        confirm_distribution(task=self.task, actor=self.actor)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)

    def _post(self, name, data):
        return self.client.post(reverse(name), data=json.dumps(data), content_type="application/json")


class ChairHeadAmendFlowTest(_DistributedTaskMixin, TestCase):
    code = "WRA"

    def test_write_without_reason_asks_for_amendment(self):
        self.client.force_login(self.head)
        response = self._post(
            "workload:row_save", {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "activity_remove": "lab"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "workload.amendment_required")
        self.row.refresh_from_db()
        self.assertEqual(self.row.lab_total, 45)
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())

    def test_remove_activity_with_amendment_then_reconfirm(self):
        self.client.force_login(self.head)
        response = self._post(
            "workload:row_save",
            {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "activity_remove": "lab", **AMEND},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.row.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual((self.row.lab_total, self.row.lab_plan, self.row.total_hours), (0, 0, 45))
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row, activity=Activity.LAB).exists())
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        amendment = WorkloadAmendment.objects.get(task=self.task)
        self.assertEqual((amendment.target_id, amendment.reason), (self.row.pk, "correction"))
        self.assertEqual(amendment.old_values["lab_total"], 45)

        response = self._post("workload:confirm", {"task_id": str(self.task.pk)})
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)

    def test_edit_hours_shrinks_assignment_only_when_asked(self):
        self.client.force_login(self.head)
        payload = {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "seminar_total": 10, **AMEND}
        response = self._post("workload:row_save", payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "workload.total_below_assigned")
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())  # tranzaksiya geri qayıtdı
        response = self._post("workload:row_save", {**payload, "shrink_assignments": "1"})
        self.assertEqual(response.status_code, 200, response.content)
        seminar = TeacherAssignment.objects.get(row=self.row, activity=Activity.SEMINAR)
        self.assertEqual(seminar.hours, 10)

    def test_add_and_remove_assignment_and_rows(self):
        self.client.force_login(self.head)
        lab = TeacherAssignment.objects.get(row=self.row, activity=Activity.LAB)
        response = self._post("workload:unassign", {"assignment_id": str(lab.pk)})
        self.assertEqual(response.status_code, 409)
        response = self._post("workload:unassign", {"assignment_id": str(lab.pk), **AMEND})
        self.assertEqual(response.status_code, 200, response.content)
        response = self._post(
            "workload:assign",
            {"row_id": str(self.row.pk), "activity": "lab", "teacher_id": "", "hours": 20, **AMEND},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(TeacherAssignment.objects.get(row=self.row, activity=Activity.LAB).hours, 20)
        # Bir sətir üçün bir düzəliş (sətir artıq hədəfdir — ikinci yazı yeni qeyd açmır).
        self.assertEqual(WorkloadAmendment.objects.filter(task=self.task).count(), 1)

        response = self._post(
            "workload:row_save",
            {"task_id": str(self.task.pk), "subject_text": "Yeni seçmə fənn", "lecture_total": 15, **AMEND},
        )
        self.assertEqual(response.status_code, 200, response.content)
        new_row = TeachingTaskRow.objects.get(pk=response.json()["row_id"])
        self.assertEqual(new_row.total_hours, 15)
        self.assertTrue(WorkloadAmendment.objects.filter(task=self.task, target_id=new_row.pk).exists())
        response = self._post("workload:row_delete", {"task_id": str(self.task.pk), "row_id": str(new_row.pk)})
        self.assertEqual(response.status_code, 200, response.content)  # yeni sətir artıq hədəfdir
        self.assertFalse(TeachingTaskRow.objects.filter(pk=new_row.pk).exists())

    def test_teacher_cannot_edit_even_with_reason(self):
        self.client.force_login(self.teacher)
        response = self._post(
            "workload:row_save",
            {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "activity_remove": "lab", **AMEND},
        )
        self.assertEqual(response.status_code, 403)
        lab = TeacherAssignment.objects.get(row=self.row, activity=Activity.LAB)
        response = self._post("workload:unassign", {"assignment_id": str(lab.pk), **AMEND})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.distribute_denied")
        self.row.refresh_from_db()
        self.assertEqual(self.row.lab_total, 45)


class RimAmendFlowTest(_DistributedTaskMixin, TestCase):
    """RİM rəhbəri (`*`, org əhatəsi) edir; RİM əməkdaşı yalnız `workload.report` ilə — yox («öz səlahiyyəti qədər»)."""

    code = "WRR"

    def test_rim_head_with_key_can_edit(self):
        rim = User.objects.create_user("wrr_rim", "wrr_rim@x.test", "pw")
        activate_member(self.org, rim, "ikt_rehber", permissions=["*"], level=95)
        self.client.force_login(rim)
        response = self._post(
            "workload:row_save",
            {
                "task_id": str(self.task.pk),
                "row_id": str(self.row.pk),
                "lab_total": 0,
                "shrink_assignments": "1",
                **AMEND,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.row.refresh_from_db()
        self.assertEqual(self.row.lab_total, 0)

    def test_rim_staff_without_key_cannot(self):
        staff = User.objects.create_user("wrr_staff", "wrr_staff@x.test", "pw")
        activate_member(self.org, staff, "rim_staff", permissions=["workload.view", "workload.report"], level=60)
        self.client.force_login(staff)
        response = self._post(
            "workload:row_save",
            {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "activity_remove": "lab", **AMEND},
        )
        self.assertEqual(response.status_code, 403)


class MyWorkloadLinesTest(_DistributedTaskMixin, TestCase):
    code = "WRL"

    def test_one_line_per_subject_and_group(self):
        self.client.force_login(self.teacher)
        payload = self.client.get(reverse("workload:my_rows"), {"year": YEAR}).json()
        self.assertEqual(len(payload["rows"]), 3)  # bölgü sətirləri (etiraz hədəfi) dəyişmir
        self.assertEqual(len(payload["lines"]), 1)
        line = payload["lines"][0]
        self.assertEqual(line["hours"], 90)
        self.assertEqual(line["activity_label"], "Mühazirə 30 · Seminar/təcrübi 15 · Laboratoriya 45")
        self.assertEqual(line["edit_url"], "")  # müəllim — yalnız oxu

    def test_chair_head_sees_edit_link_to_the_row(self):
        # Kafedra müdiri həm də öz kafedrasının müəllimidir — yeni sətir + bölgü düzəliş axını ilə.
        activate_member(
            self.org,
            self.head,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        amend = {"reason": "official", "note": "Yeni seçmə fənn"}
        row = save_row_amended(
            task=self.task, actor=self.actor, data={"subject_text": "Seçmə fənn", "lecture_total": 30}, amend=amend
        )
        assign_amended(row=row, actor=self.actor, amend=amend, activity="lecture", teacher_id=self.head.pk, hours=30)
        confirm_distribution(task=self.task, actor=self.actor)
        self.client.force_login(self.head)
        payload = self.client.get(reverse("workload:my_rows"), {"year": YEAR}).json()
        self.assertEqual(len(payload["lines"]), 1)
        url = payload["lines"][0]["edit_url"]
        self.assertIn("section=workload-distribution", url)
        self.assertIn(f"chair={self.stack['chair'].pk}", url)
        self.assertIn(f"row={row.pk}", url)

        html = self.client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-workload"})).json()[
            "html"
        ]
        self.assertIn("Redaktə et", html)

    def test_grouping_merges_split_activity_and_keeps_single_label(self):
        rows = [
            {"id": "a1", "row_id": "r1", "activity": "lab", "activity_label": "Laboratoriya", "hours": 15},
            {"id": "a2", "row_id": "r1", "activity": "lab", "activity_label": "Laboratoriya", "hours": 15},
            {"id": "a3", "row_id": "r2", "activity": "lecture", "activity_label": "Mühazirə", "hours": 30},
        ]
        lines = {line["row_id"]: line for line in group_workload_lines(rows)}
        self.assertEqual((lines["r1"]["hours"], lines["r1"]["activity_label"]), (30, "Laboratoriya"))
        self.assertEqual(lines["r1"]["assignment_ids"], ["a1", "a2"])
        self.assertEqual(lines["r2"]["activity_label"], "Mühazirə")


class FixTaskRowHoursCommandTest(_DistributedTaskMixin, TestCase):
    code = "WRF"

    def setUp(self):
        super().setUp()
        self.root = User.objects.create_superuser("wrf_root", "wrf_root@x.test", "pw")
        self.stack["group"].name = "631/5K"
        self.stack["group"].save(update_fields=["name"])
        self.offering = CourseOffering.objects.get(organization=self.org, group=self.stack["group"])
        self.assertEqual(self.offering.instructor_id, self.teacher.pk)

    def _call(self, *extra, group="631/5K"):
        out = StringIO()
        call_command(
            "fix_task_row_hours",
            "--org", self.org.slug, "--year", YEAR, "--chair", self.stack["chair"].name,
            "--group", group, "--subject", self.stack["subject"].name, "--activity", "lab", "--hours", "0",
            "--reason", "TAPŞIRIQ kitabçasında lab xanasına cəm yazılıb", "--actor", "wrf_root",
            *extra, stdout=out,
        )  # fmt: skip
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        output = self._call()
        self.assertIn("DRY-RUN", output)
        self.assertIn("rows_changed=1", output)
        self.row.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.row.lab_total, 45)
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertTrue(TeacherAssignment.objects.filter(row=self.row, activity=Activity.LAB).exists())
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())

    def test_apply_sets_lab_zero_removes_assignment_keeps_instructor(self):
        output = self._call("--apply")
        self.assertIn("APPLY", output)
        self.assertIn("reconfirmed=1", output)
        self.assertNotIn(self.teacher.username, output)
        self.row.refresh_from_db()
        self.task.refresh_from_db()
        self.offering.refresh_from_db()
        self.assertEqual((self.row.lab_total, self.row.total_hours), (0, 45))
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row, activity=Activity.LAB).exists())
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row).count(), 2)
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(self.offering.instructor_id, self.teacher.pk)
        self.assertEqual(WorkloadAmendment.objects.filter(task=self.task).count(), 1)
        # İdempotent.
        self.assertIn("unchanged=1", self._call("--apply"))

    def test_unknown_or_ambiguous_group_token_writes_nothing(self):
        with self.assertRaises(CommandError):
            self._call("--apply", group="631/5K,631/5K ing")
        self.row.refresh_from_db()
        self.assertEqual(self.row.lab_total, 45)
