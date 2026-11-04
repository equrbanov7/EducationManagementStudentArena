"""2026-11-04: etirazlı sətrin silinməsi 500 verirdi.

``POST /ders-yuku/setir/sil/`` → ``row.delete()`` → ``LoadObjection.row`` CASCADE → append-only trigger
(``workload_objection_append_only``) etirazın DELETE-ini qadağan edir → DB xətası → HTTP 500 (prod sətri
9ec1f98f…: 1 etiraz, 2 bölgü). İndi silmədən ƏVVƏL yoxlanılır və aydın 409 (``workload.row_has_objections``)
qaytarılır, heç nə silinmir. Bölgünün silinməsi isə təhlükəsizdir (``assignment`` FK-si SET NULL — trigger buna
icazə verir), ona görə «sətri söndür» (fəaliyyətləri çıxar / saatları 0 et) alternativi işləyir və etiraz qalır.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.workload.constants import Activity
from apps.workload.models import LoadObjection, TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from apps.workload.services import WorkloadDenied, delete_row, resolve_actor
from apps.workload.services.tasks import ROW_HAS_OBJECTIONS
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from .test_row_edit_amend_2026_10_15 import AMEND, CHAIR_PERMS, _DistributedTaskMixin

User = get_user_model()

OBJECTION_TEXT = "Bu yük mənim deyil, laboratoriya başqa müəllimdədir."


def _object(row, teacher, assignment=None):
    return LoadObjection.objects.create(
        organization=row.organization,
        row=row,
        assignment=assignment,
        teacher=teacher,
        reason_key="other",
        text=OBJECTION_TEXT,
    )


def _post(client, name, data):
    return client.post(reverse(name), data=json.dumps(data), content_type="application/json")


class DraftRowDeleteObjectionTest(TestCase):
    """Qaralama sənəd: etirazlı sətir silinmir (409), etirazsız sətir əvvəlki kimi silinir."""

    def setUp(self):
        self.org = make_org("wl-rdo")
        self.stack = make_structure(self.org, code="RDO")
        self.head = User.objects.create_user("rdo_head", "rdo_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("rdo_teacher", "rdo_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS + ["workload.object"],
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30)
        self.lecture = TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity=Activity.LECTURE, hours=30
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity=Activity.SEMINAR, hours=30
        )
        self.client.force_login(self.head)

    def test_row_with_objection_returns_409_and_deletes_nothing(self):
        objection = _object(self.row, self.teacher, assignment=self.lecture)
        response = _post(self.client, "workload:row_delete", {"task_id": str(self.task.pk), "row_id": str(self.row.pk)})
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["error"], ROW_HAS_OBJECTIONS)
        self.assertIn("etiraz", body["message"])
        self.assertTrue(TeachingTaskRow.objects.filter(pk=self.row.pk).exists())
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row).count(), 2)
        objection.refresh_from_db()
        self.assertEqual((objection.row_id, objection.assignment_id), (self.row.pk, self.lecture.pk))

    def test_service_refuses_for_batch_callers_too(self):
        _object(self.row, self.teacher)
        with self.assertRaises(WorkloadDenied) as ctx:
            delete_row(task=self.task, row=self.row, actor=resolve_actor(self.head, self.org))
        self.assertEqual(ctx.exception.code, ROW_HAS_OBJECTIONS)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=self.row.pk).exists())

    def test_row_without_objection_still_deletes(self):
        response = _post(self.client, "workload:row_delete", {"task_id": str(self.task.pk), "row_id": str(self.row.pk)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(TeachingTaskRow.objects.filter(pk=self.row.pk).exists())
        self.assertFalse(TeacherAssignment.objects.filter(row_id=self.row.pk).exists())

    def test_objection_on_another_row_does_not_block(self):
        other = make_row(self.task, self.stack, lecture_total=15, seminar_total=0)
        _object(other, self.teacher)
        response = _post(self.client, "workload:row_delete", {"task_id": str(self.task.pk), "row_id": str(self.row.pk)})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(TeachingTaskRow.objects.filter(pk=self.row.pk).exists())
        self.assertTrue(LoadObjection.objects.filter(row=other).exists())


class DistributedRowDeleteObjectionTest(_DistributedTaskMixin, TestCase):
    """Təsdiqlənmiş sənəd (prod halı): səbəbli silmə də 409; düzəliş qeydi açılmır; «söndür» yolu işləyir."""

    code = "RDD"

    def setUp(self):
        super().setUp()
        self.lab = TeacherAssignment.objects.get(row=self.row, activity=Activity.LAB)
        self.objection = _object(self.row, self.teacher, assignment=self.lab)
        self.client.force_login(self.head)

    def test_amended_delete_returns_409_without_opening_amendment(self):
        response = self._post(
            "workload:row_delete", {"task_id": str(self.task.pk), "row_id": str(self.row.pk), **AMEND}
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], ROW_HAS_OBJECTIONS)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=self.row.pk).exists())
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row).count(), 3)
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())

    def test_unassign_objected_assignment_keeps_objection_history(self):
        # Trigger FK təmizliyinə (SET NULL) icazə verir — etirazı həll etmək üçün yükü başqasına vermək lazımdır,
        # ona görə bölgünün silinməsi bloklanmır; etiraz sətirdə qalır, mətni dəyişmir.
        response = self._post("workload:unassign", {"assignment_id": str(self.lab.pk), **AMEND})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(TeacherAssignment.objects.filter(pk=self.lab.pk).exists())
        self.objection.refresh_from_db()
        self.assertEqual((self.objection.row_id, self.objection.assignment_id), (self.row.pk, None))
        self.assertEqual(self.objection.text, OBJECTION_TEXT)

    def test_retire_row_by_removing_activities(self):
        for activity in ("lecture", "seminar", "lab"):
            response = self._post(
                "workload:row_save",
                {"task_id": str(self.task.pk), "row_id": str(self.row.pk), "activity_remove": activity, **AMEND},
            )
            self.assertEqual(response.status_code, 200, response.content)
        self.row.refresh_from_db()
        self.assertEqual((self.row.lecture_total, self.row.seminar_total, self.row.lab_total), (0, 0, 0))
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row).exists())
        self.objection.refresh_from_db()
        self.assertEqual((self.objection.row_id, self.objection.text), (self.row.pk, OBJECTION_TEXT))
