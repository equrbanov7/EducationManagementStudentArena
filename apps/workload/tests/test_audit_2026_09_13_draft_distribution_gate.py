"""Audit 2026-09-13 tests F-T1 (P1) — göndərilməmiş TŞ qaralaması kafedra tərəfindən bölünə bilməz.

Əvvəl `ensure_distribution_stage` qaralama istisnasını yalnız `submitted_at`
ilə yoxlayırdı: tədris şöbəsinin yaratdığı, hələ göndərilməmiş tapşırığı
kafedra müdiri bölüb «distributed» edir və `sync_offerings` açılış yaradırdı —
koordinator vizası və dekan təsdiqi tam ötürülürdü. İstisna indi yalnız
kafedranın ÖZÜ yaratdığı (yaradanın `workload.distribute` əhatəsi olan)
qaralamalar üçündür; `confirm_distribution` də eyni qapıdan keçir.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.workload.constants import Activity, TaskStatus
from apps.workload.services import WorkloadDenied, assign_teacher, confirm_distribution, resolve_actor
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]


class DraftDistributionGateTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-ft1")
        self.stack = make_structure(self.org, code="WLF")
        self.head = User.objects.create_user("wlf_head", "wlf_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.office = User.objects.create_user("wlf_office", "wlf_office@x.test", "pw")
        activate_member(
            self.org,
            self.office,
            "teaching_office",
            permissions=OFFICE_PERMS,
            level=75,
            scope_type=RoleScopeType.ORGANIZATION,
        )
        self.teacher = User.objects.create_user("wlf_teacher", "wlf_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.chair_actor = resolve_actor(self.head, self.org)

    def _assign(self, row):
        return assign_teacher(
            row=row, actor=self.chair_actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=30
        )

    def test_office_draft_not_yet_submitted_cannot_be_distributed_by_chair(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        with self.assertRaises(WorkloadDenied) as ctx:
            self._assign(row)
        self.assertEqual(ctx.exception.code, "workload.not_approved_yet")
        with self.assertRaises(WorkloadDenied) as ctx:
            confirm_distribution(task=task, actor=self.chair_actor)
        self.assertEqual(ctx.exception.code, "workload.not_approved_yet")
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DRAFT)

    def test_draft_without_creator_is_closed_too(self):
        task = make_task(self.org, self.stack["chair"], created_by=None)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        with self.assertRaises(WorkloadDenied):
            self._assign(row)

    def test_chair_own_draft_keeps_the_legacy_exception(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.head)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        self._assign(row)
        result = confirm_distribution(task=task, actor=self.chair_actor)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(result["sync"]["created"], 1)

    def test_approved_task_distributes_regardless_of_creator(self):
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.office)
        row = make_row(task, self.stack, lecture_total=30, seminar_total=0)
        self._assign(row)
        confirm_distribution(task=task, actor=self.chair_actor)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DISTRIBUTED)
