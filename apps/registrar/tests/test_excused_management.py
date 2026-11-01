"""Reason-only RİM attendance controls retain correction evidence and tenant scope."""

import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit, Role
from apps.registrar import corrections, excused_management, gradebook
from apps.registrar.models import CorrectionField, CorrectionReversal, JournalCorrection, LessonMark
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup, _pdf
from core.rls import bypass_rls, journal_unlock


class ExcusedManagementTests(_BaseJournalSetup):
    def setUp(self):
        super().setUp()
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = self.settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.manager = get_user_model().objects.create_user("excused-rim")
        Membership.objects.create(
            organization=self.org, user=self.manager, role=self.org.roles.get(name="ikt_rehber"), is_active=True
        )
        self.lesson, self.mark = self._absent_lesson(9, hours=2)
        with journal_unlock():
            LessonMark.objects.filter(pk=self.mark.pk).update(status="excused")
        self.mark.refresh_from_db()
        gradebook.recompute_absence_hours(enrollment=self.enrollment)

    def request(self, user=None, permissions=None):
        user = user or self.manager
        request = RequestFactory().post("/")
        request.user, request.organization = user, self.org
        request.org_memberships = list(
            Membership.objects.filter(organization=self.org, user=user, is_active=True).select_related("role")
        )
        request.org_permissions = (
            permissions if permissions is not None else [p for m in request.org_memberships for p in m.role.permissions]
        )
        return request

    def manage(self, **kwargs):
        return excused_management.manage(
            request=kwargs.pop("request", self.request()),
            offering=self.offering,
            mark_id=self.mark.pk,
            operation=kwargs.pop("operation", "change"),
            reason=kwargs.pop("reason", "Səhv üzrlü qeyd yoxlanıldı"),
            expected_status=kwargs.pop("expected_status", "excused"),
            expected_correction_id=kwargs.pop("expected_correction_id", ""),
            new_status=kwargs.pop("new_status", "absent"),
            **kwargs,
        )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_rim_reason_only_change_and_exact_reversal_keep_evidence_and_scores(self):
        _, unrelated = self._seminar_mark(10, 8)
        original_count = JournalCorrection.objects.count()
        correction = self.manage()
        self.mark.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual((self.mark.status, self.mark.score, self.enrollment.absence_hours), ("absent", None, 2))
        self.assertEqual((correction.old_status, correction.new_status), ("excused", "absent"))
        self.assertEqual(correction.corrected_by_id, self.manager.pk)
        self.assertEqual(correction.note, "Səhv üzrlü qeyd yoxlanıldı")
        self.assertTrue(correction.document)
        import fitz

        with correction.document.open("rb") as stream:
            with fitz.open(stream=stream.read(), filetype="pdf") as document:
                self.assertIn("Rəsmi əsas sənədi yüklənməyib", document[0].get_text())
        self.manage(
            operation="reverse",
            expected_status="absent",
            expected_correction_id=str(correction.pk),
            reason="Əvvəlki üzrlü qərar qüvvədədir",
        )
        self.mark.refresh_from_db()
        self.enrollment.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual((self.mark.status, self.enrollment.absence_hours, unrelated.score), ("excused", 0, 8))
        reversal = CorrectionReversal.objects.get(journal_correction=correction)
        self.assertEqual(reversal.reason_note, "Əvvəlki üzrlü qərar qüvvədədir")
        self.assertEqual(JournalCorrection.objects.count(), original_count + 1)
        self.assertTrue(AuditLog.objects.filter(new_values__reason_note=reversal.reason_note).exists())
        self.manage(
            operation="reverse",
            expected_status="absent",
            expected_correction_id=str(correction.pk),
            reason="Əvvəlki üzrlü qərar qüvvədədir",
        )
        self.assertEqual(CorrectionReversal.objects.count(), 1)
        self.login(self.teacher)
        history = self.client.get(reverse("registrar:journal_history", args=[self.offering.pk]))
        self.assertEqual(history.status_code, 200)
        labels = " ".join(entry["kind_label"] for entry in history.json()["entries"])
        self.assertIn(correction.note, labels)
        self.assertIn(reversal.reason_note, labels)

    def test_revert_original_documented_excuse_preserves_original_medical_document(self):
        with journal_unlock():
            LessonMark.objects.filter(pk=self.mark.pk).update(status="absent")
        self.mark.refresh_from_db()
        original = corrections.apply_correction(
            mark=self.mark,
            field="attendance",
            new_status="excused",
            reason="medical",
            note="Original medical evidence",
            document=_pdf(),
            by_user=self.admin,
        )
        document_name = original.document.name
        self.manage(operation="reverse", expected_correction_id=str(original.pk))
        original.refresh_from_db()
        self.mark.refresh_from_db()
        self.assertEqual(
            (self.mark.status, original.document.name, original.note),
            ("absent", document_name, "Original medical evidence"),
        )
        self.assertTrue(original.document.storage.exists(document_name))

    def test_required_reason_and_stale_or_score_payload_cannot_change_data(self):
        for reason in ("", "  x  ", "x" * 501):
            with self.assertRaises(ValidationError):
                self.manage(reason=reason)
        for status in ("excused", "clear", "99", ""):
            with self.assertRaises(ValidationError):
                self.manage(new_status=status)
        with self.assertRaises(ValidationError):
            self.manage(expected_status="absent")
        correction = self.manage()
        with self.assertRaises(ValidationError):
            self.manage()
        self.assertEqual(JournalCorrection.objects.count(), 1)
        self.assertEqual(CorrectionReversal.objects.count(), 0)
        self.assertEqual(correction.field, CorrectionField.ATTENDANCE)

    def test_teacher_student_and_corrector_without_narrow_permission_denied(self):
        for user in (self.teacher, self.student):
            with self.assertRaises(PermissionDenied):
                self.manage(request=self.request(user))
        role = Role.objects.create(
            organization=self.org,
            name="document-corrector",
            display_name="Corrector",
            permissions=["journal.correct"],
            scope_type="organization",
        )
        operator = get_user_model().objects.create_user("excused-corrector")
        Membership.objects.create(organization=self.org, user=operator, role=role, is_active=True)
        with self.assertRaises(PermissionDenied):
            self.manage(request=self.request(operator))
        self.assertEqual(JournalCorrection.objects.count(), 0)

    def test_unit_scope_is_enforced_and_other_tenant_context_is_denied(self):
        unit = OrgUnit.objects.create(organization=self.org, name="Other", slug="excused-other", unit_type="faculty")
        role = Role.objects.create(
            organization=self.org,
            name="scoped-excuse",
            display_name="Scoped",
            permissions=[excused_management.PERMISSION],
            scope_type="unit",
        )
        operator = get_user_model().objects.create_user("excused-scoped")
        membership = Membership.objects.create(
            organization=self.org, user=operator, role=role, scope_unit=unit, is_active=True
        )
        with self.assertRaises(PermissionDenied):
            self.manage(request=self.request(operator))
        membership.scope_unit = self.group
        membership.save()
        operator = get_user_model().objects.get(pk=operator.pk)
        self.assertTrue(excused_management.can_manage(self.request(operator), self.offering))
        request = self.request()
        request.organization = None
        with self.assertRaises(PermissionDenied):
            self.manage(request=request)

    def test_reverse_requires_exact_latest_excused_related_correction(self):
        with journal_unlock():
            self.lesson.kind = "seminar"
            self.lesson.save(update_fields=["kind"])
        first = self.manage(new_status="present")
        self.mark.refresh_from_db()
        latest = corrections.apply_correction(
            mark=self.mark,
            field="score",
            new_score=8,
            reason="technical",
            note="Later official score",
            document=_pdf(),
            by_user=self.admin,
        )
        with self.assertRaises(ValidationError):
            self.manage(operation="reverse", expected_status="present", expected_correction_id=str(first.pk))
        with self.assertRaises(ValidationError):
            self.manage(operation="reverse", expected_status="present", expected_correction_id=str(latest.pk))
        self.assertFalse(CorrectionReversal.objects.exists())

    def test_ledger_reason_is_database_immutable_and_legacy_reason_stays_empty(self):
        correction = self.manage()
        self.manage(operation="reverse", expected_status="absent", expected_correction_id=str(correction.pk))
        reversal = CorrectionReversal.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            CorrectionReversal.objects.filter(pk=reversal.pk).update(reason_note="Rewritten history")
        reversal.refresh_from_db()
        self.assertEqual(reversal.reason_note, "Səhv üzrlü qeyd yoxlanıldı")
        _, mark = self._seminar_mark(11, 3)
        legacy = corrections.apply_correction(
            mark=mark,
            field="score",
            new_score=4,
            reason="technical",
            note="Existing path",
            document=_pdf(),
            by_user=self.admin,
        )
        corrections.revert_last_grade_correction(mark=mark, by_user=self.admin, correction_id=legacy.pk)
        self.assertEqual(CorrectionReversal.objects.get(journal_correction=legacy).reason_note, "")

    def test_audit_failure_rolls_back_status_and_evidence(self):
        with patch("apps.registrar.corrections.grade_audit.log_grade_changes", side_effect=RuntimeError("audit down")):
            with self.assertRaises(RuntimeError):
                self.manage()
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.status, "excused")
        self.assertFalse(JournalCorrection.objects.exists())

    def test_http_rim_control_visible_teacher_readonly_and_csrf_required(self):
        self.login(self.manager)
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-excused-open")
        self.assertContains(response, "data-excused-modal")
        action = reverse("registrar:excused_management", args=[self.offering.pk])
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        session = csrf_client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(csrf_client.post(action, {}).status_code, 403)
        self.login(self.teacher)
        response = self.client.get(url)
        self.assertNotContains(response, "data-excused-open")
        self.assertNotContains(response, "data-excused-modal")
        self.assertEqual(self.client.post(action, {"mark_id": str(self.mark.pk)}).status_code, 404)
        self.login(self.manager)
        response = self.client.post(
            action,
            {
                "mark_id": str(self.mark.pk),
                "operation": "change",
                "new_status": "absent",
                "expected_status": "excused",
                "expected_correction_id": "",
                "reason": "Sənədsiz yoxlanmış düzəliş",
                "new_score": "10",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.mark.refresh_from_db()
        self.assertEqual((self.mark.status, self.mark.score), ("absent", None))

    def test_generic_reverse_endpoint_cannot_bypass_required_excused_reason(self):
        correction = self.manage()
        self.login(self.manager)
        url = reverse("registrar:correction_delete", args=[self.offering.pk])
        payload = {"type": "grade", "mark_id": str(self.mark.pk), "correction_id": str(correction.pk)}
        self.assertEqual(self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 409)
        self.assertFalse(CorrectionReversal.objects.exists())
        payload["reason"] = "Geri alma üçün yoxlanmış səbəb"
        self.assertEqual(self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        self.assertEqual(CorrectionReversal.objects.get().reason_note, payload["reason"])

    def test_reversing_an_excused_created_empty_cell_retains_evidence_and_retry(self):
        from apps.registrar.models import Lesson

        lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, date="2024-10-20", kind="lecture", hours=2
        )
        mark = LessonMark(organization=self.org, lesson=lesson, enrollment=self.enrollment)
        correction = corrections.apply_correction(
            mark=mark,
            field="attendance",
            new_status="excused",
            reason="medical",
            note="Documented new cell",
            document=_pdf(),
            by_user=self.admin,
            was_empty=True,
        )
        self.mark = mark
        self.manage(
            operation="reverse",
            expected_correction_id=str(correction.pk),
            reason="Təsadüfən yaradılmış xana geri alındı",
        )
        self.assertFalse(LessonMark.objects.filter(pk=mark.pk).exists())
        self.assertTrue(JournalCorrection.objects.filter(pk=correction.pk).exists())
        self.manage(
            operation="reverse",
            expected_correction_id=str(correction.pk),
            reason="Təsadüfən yaradılmış xana geri alındı",
        )
        self.assertEqual(CorrectionReversal.objects.filter(journal_correction=correction).count(), 1)
        with self.assertRaises(ValidationError):
            self.manage(
                operation="reverse", expected_correction_id=str(correction.pk), reason="Dəyişdirilmiş yeni səbəb"
            )

    def test_teacher_full_edit_still_cannot_override_excused(self):
        result = gradebook.save_marks(
            offering=self.offering,
            entries=[
                {
                    "lesson_id": str(self.lesson.pk),
                    "enrollment_id": str(self.enrollment.pk),
                    "status": "present",
                    "score": "10",
                }
            ],
            by_user=self.teacher,
            full_edit=True,
            full_reason="Teacher reason remains insufficient",
            enforce_day=False,
            report=True,
        )
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.status, "excused")
        self.assertEqual(result["written"], 0)
