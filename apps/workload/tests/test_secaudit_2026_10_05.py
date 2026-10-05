"""Təhlükəsizlik auditi 2026-10-05 — dərs yükü."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.workload.constants import Activity, AmendmentReason, AmendmentTarget, TaskStatus
from apps.workload.models import WorkloadAmendment
from apps.workload.services import WorkloadDenied, assign_teacher, confirm_distribution, open_amendment, resolve_actor
from core.constants import RoleScopeType

from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class AmendmentDocumentValidationTest(TestCase):
    """``FileField.validators`` ``save()``-də işləmir — sənəd servisdə yoxlanmalıdır."""

    def setUp(self):
        self.org = make_org("wl-secaudit")
        self.stack = make_structure(self.org, code="WLS")
        self.head = User.objects.create_user("wls_head", "wls_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=10, seminar_total=0)
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=None, hours=10)
        confirm_distribution(task=self.task, actor=self.actor)
        self.task.refresh_from_db()

    def _amend(self, document):
        return open_amendment(
            task=self.task,
            actor=self.actor,
            target_kind=AmendmentTarget.ROW,
            target_id=self.row.pk,
            reason=AmendmentReason.CORRECTION,
            note="Sənədlə düzəliş",
            document=document,
        )

    def test_html_document_is_rejected(self):
        evil = SimpleUploadedFile("order.html", b"<script>alert(1)</script>", content_type="application/pdf")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._amend(evil)
        self.assertEqual(ctx.exception.code, "workload.invalid_document")
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())

    def test_non_pdf_content_with_pdf_name_is_rejected(self):
        fake = SimpleUploadedFile(
            "order.pdf", b"<html><script>alert(1)</script></html>", content_type="application/pdf"
        )
        with self.assertRaises(WorkloadDenied):
            self._amend(fake)
