"""Qrup çekmecəsi «Qrupdan çıxar» (sahib 2026-11-25) — ``group_action`` ``remove_student`` / ``remove_extra``.

Sahib: «sadəcə qrupdan çıxarmaq» — xaric / dondurma / məzun DEYİL: status «Qeydiyyatlı» qalır, tələbə qrupsuz olur
və «Tələbə əlavə et» namizədlərində (qrupsuzlar) görünür. Əlavə üzv isə yalnız bu qrupun jurnallarından çıxır.
"""

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    GroupTransferEvidence,
    JournalRemoval,
    StudentAcademicRecord,
    StudentMovement,
)

from .test_groups_registry_add_students import _AddStudentsBase
from .test_teaching_office_stage2 import PASSWORD

REASON = "Tələbə ərizə ilə qrupdan çıxır, yeni qrup sonra təyin olunacaq."


class _RemoveBase(_AddStudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Kafedra müdiri — qrup idarəsi YALNIZ öz kafedrası əhatəsində (``far_group`` kənardadır).
        chair = cls.roles["chair_head"]
        chair.permissions = list(chair.permissions) + ["unit.group_manage"]
        chair.save(update_fields=["permissions"])

    def _remove(self, record, *, role="teaching_office_head", group=None, action="remove_student", **extra):
        payload = {
            "action": action,
            "id": str((group or self.group).id),
            "record_id": str(record.id),
            "reason": REASON,
        }
        payload.update(extra)
        return self._action(role, payload)


class RemoveStudentActionTest(_RemoveBase):
    def setUp(self):
        super().setUp()
        self.record = self.students[0]
        self.enrollment = Enrollment.objects.create(
            organization=self.org,
            student=self.record.student,
            offering=self.offering,
            status=Enrollment.Status.ENROLLED,
        )

    def test_student_becomes_groupless_and_stays_enrolled(self):
        response = self._remove(self.record, order_number="5/Q", order_date="2026-11-25")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["moved"], 1)
        self.record.refresh_from_db()
        self.assertIsNone(self.record.group_id)
        self.assertEqual(self.record.status, "enrolled")
        self.assertTrue(self.record.is_active)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.DROPPED)
        self.assertFalse(StudentMovement.objects.filter(record=self.record).exists())
        evidence = GroupTransferEvidence.objects.get(record=self.record)
        self.assertIsNone(evidence.new_group_id)
        self.assertTrue(evidence.is_finalized)
        group_audit = AuditLog.objects.filter(
            organization=self.org, user=self.users["teaching_office_head"], reason__startswith="groups: student removed"
        ).get()
        self.assertEqual(group_audit.new_values["order_number"], "5/Q")
        # Çekmecədə yoxdur, «Tələbə əlavə et» namizədlərində (qrupsuzlar) var.
        rows = self._client("teaching_office_head").get(self._students_url()).json()["rows"]
        self.assertNotIn(self.record.student.username, {row["username"] for row in rows})
        candidates = self._client("teaching_office_head").get(self._candidates_url(self.group_b)).json()["results"]
        self.assertIn(str(self.record.id), {row["id"] for row in candidates})

    def test_short_reason_is_rejected(self):
        response = self._remove(self.record, reason="qısa")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "reason_too_short")
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.id)

    def test_bad_order_date_is_rejected(self):
        response = self._remove(self.record, order_date="25.11.2026x")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "order_date_invalid")

    def test_dean_without_group_manage_is_403(self):
        response = self._remove(self.record, role="dean")
        self.assertEqual(response.status_code, 403, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.id)

    def test_scoped_manager_removes_inside_own_chair(self):
        response = self._remove(self.record, role="chair_head")
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertIsNone(self.record.group_id)

    def test_group_outside_manage_scope_is_404(self):
        far = self._far_record()
        response = self._remove(far, role="chair_head", group=self.far_group)
        self.assertEqual(response.status_code, 404, response.content)
        far.refresh_from_db()
        self.assertEqual(far.group_id, self.far_group.id)

    def test_record_of_another_group_is_404(self):
        far = self._far_record()
        response = self._remove(far)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["error"], "not_in_group")
        far.refresh_from_db()
        self.assertEqual(far.group_id, self.far_group.id)

    def test_groupless_record_is_404(self):
        response = self._remove(self.free[0])
        self.assertEqual(response.status_code, 404, response.content)

    def _far_record(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user("ds2_far0", "ds2_far0@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=user, organization=self.org, role=self.roles["teacher"], is_primary=True, is_active=True
        )
        return StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program,
            curriculum=self.plan,
            group=self.far_group,
            admission_year=2024,
        )


class RemoveExtraMemberActionTest(_RemoveBase):
    def setUp(self):
        super().setUp()
        self.offering_b = CourseOffering.objects.create(
            organization=self.org, subject=self.subject_b, period=self.period, group=self.group_b
        )
        self.record = self.students[0]
        added = self._action(
            "teaching_office_head",
            {
                "action": "add_students",
                "id": str(self.group_b.id),
                "record_ids": "x:" + str(self.record.id),
                "other_mode": "extra",
            },
        )
        self.assertEqual(added.json()["extra"], 1, added.content)

    def test_extra_member_leaves_group_journals_but_keeps_home_group(self):
        response = self._remove(self.record, group=self.group_b, action="remove_extra")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["removed"], 1)
        enrollment = Enrollment.objects.get(student=self.record.student, offering=self.offering_b)
        self.assertEqual(enrollment.status, Enrollment.Status.DROPPED)
        self.assertTrue(JournalRemoval.objects.filter(enrollment=enrollment).exists())
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.id)  # öz qrupu dəyişmir
        self.assertFalse(GroupTransferEvidence.objects.filter(record=self.record).exists())
        drawer = self._client("teaching_office_head").get(self._students_url(self.group_b)).json()
        self.assertEqual(drawer["extra_rows"], [])

    def test_home_member_is_not_an_extra_member(self):
        response = self._remove(self.students[1], action="remove_extra")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "not_extra")

    def test_extra_row_cannot_use_home_removal(self):
        response = self._remove(self.record, group=self.group_b, action="remove_student")
        self.assertEqual(response.status_code, 404, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group.id)

    def test_extra_removal_outside_manage_scope_is_404(self):
        response = self._remove(self.record, role="chair_head", group=self.far_group, action="remove_extra")
        self.assertEqual(response.status_code, 404, response.content)
        enrollment = Enrollment.objects.get(student=self.record.student, offering=self.offering_b)
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)

    def test_dean_cannot_remove_extra_member(self):
        response = self._remove(self.record, role="dean", group=self.group_b, action="remove_extra")
        self.assertEqual(response.status_code, 403, response.content)


class RemoveDialogsRenderTest(_RemoveBase):
    def test_registry_renders_remove_dialogs(self):
        html = self._fragment("teaching_office_head", "groups-registry").json()["html"]
        self.assertIn('id="tofGroupRemoveDialog"', html)
        self.assertIn('id="tofGroupRemoveExtraDialog"', html)
        self.assertIn('name="order_number"', html)
