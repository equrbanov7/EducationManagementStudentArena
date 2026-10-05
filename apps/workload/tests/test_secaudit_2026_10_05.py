"""Təhlükəsizlik auditi 2026-10-05 — dərs yükü."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from apps.workload.constants import Activity, AmendmentReason, AmendmentTarget, TaskStatus
from apps.workload.models import WorkloadAmendment
from apps.workload.services import WorkloadDenied, assign_teacher, confirm_distribution, open_amendment, resolve_actor
from core.constants import RoleScopeType

from .factories import YEAR, activate_member, make_org, make_row, make_structure, make_task

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

    def test_valid_pdf_document_is_stored(self):
        """Yol ~131 simvoldur (`workload_amendments/<org>/<task>/<uuid32>.pdf`) —
        sahə `max_length=100` olanda hər yükləmə `DataError` (500) verirdi."""
        from django.test import override_settings

        pdf = SimpleUploadedFile(
            "emr.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", content_type="application/pdf"
        )
        with override_settings(
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            }
        ):
            amendment = self._amend(pdf)
            amendment.refresh_from_db()
        self.assertGreater(len(amendment.document.name), 100)
        self.assertTrue(amendment.document.name.endswith(".pdf"))


class ForeignUnitSelectionTest(TestCase):
    """``wc_chair`` / ``wa_faculty`` GET parametrləri aktorun əhatəsi ilə kəsişdirilməlidir.

    Əvvəl kafedra müdiri A ``?wc_chair=<B>`` ilə B kafedrasının yük tapşırığını
    (sətirlər, müəllim bölgüsü, saatlar), dekan A isə ``?wa_faculty=<B>`` ilə B
    fakültəsinin təsdiq dilimlərini oxuyurdu.
    """

    def setUp(self):
        self.org = make_org("wl-secaudit-idor")
        self.stack_a = make_structure(self.org, code="WIA")
        self.stack_b = make_structure(self.org, code="WIB")
        self.task_b = make_task(self.org, self.stack_b["chair"], status=TaskStatus.DRAFT)
        make_row(self.task_b, self.stack_b)
        self.head = User.objects.create_user("wia_head", "wia_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack_a["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.dean = User.objects.create_user("wia_dean", "wia_dean@x.test", "pw")
        activate_member(
            self.org,
            self.dean,
            "dean",
            permissions=["workload.view", "workload.approve"],
            scope_unit=self.stack_a["faculty"],
            level=75,
            scope_type=RoleScopeType.UNIT,
        )

    def _request(self, user, **params):
        request = RequestFactory().get("/accounts/profile/", params)
        request.user = user
        request.session = {}
        request.organization = self.org
        return request

    def test_chair_head_cannot_open_other_chairs_task(self):
        from apps.workload.center_registry import build_center

        payload = build_center(
            self._request(self.head, wc_view="tasks", wc_year=YEAR, wc_chair=str(self.stack_b["chair"].pk)),
            self.org,
        )
        self.assertTrue(payload["has_access"])
        self.assertTrue(payload["task"] is None or payload["task"]["id"] != str(self.task_b.pk))
        self.assertEqual(payload["rows"], [])

    def test_dean_cannot_select_other_faculty(self):
        from apps.workload.approval_registry import build_approval

        payload = build_approval(
            self._request(self.dean, wa_year=YEAR, wa_faculty=str(self.stack_b["faculty"].pk)), self.org
        )
        self.assertTrue(payload["has_access"])
        self.assertNotEqual(payload["faculty_id"], str(self.stack_b["faculty"].pk))

    def test_dean_can_select_own_faculty(self):
        from apps.workload.approval_registry import build_approval

        faculty_a = str(self.stack_a["faculty"].pk)
        payload = build_approval(self._request(self.dean, wa_year=YEAR, wa_faculty=faculty_a), self.org)
        self.assertEqual(payload["faculty_id"], faculty_a)
