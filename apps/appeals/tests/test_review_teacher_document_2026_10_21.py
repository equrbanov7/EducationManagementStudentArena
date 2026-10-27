"""2026-10-21 (sahib) — apellyasiya qərarı: qərarı verən müəllim, əsaslandırıcı sənəd, fənni tədris edən, bildirişlər.

* «Qərarı verən müəllim» məcburidir, item-ə və ``AppealDecisionRecord``-a yazılır, auditdə (qərar + bal düzəlişi)
  var, tarixçədə, tələbənin detalında və idarə siyahısında görünür;
* «Əsaslandırıcı sənəd» defolt opsionaldır; ``exam.appeal_document_required`` yandırılanda məcburidir; tip/ölçü
  yoxlanır; yalnız apellyasiya heyəti / superadmin endirir;
* «Fənni tədris edən» tələbənin qrupunun açılışından hesablanır (yalnız aktiv), seçicidə ilk/defolt variantdır;
* müəllim öz açılışının apellyasiyalarını yalnız-oxu görür; başqası görmür;
* bildirişlər: müraciət → fənn müəllimi + mərkəz; qərar → fənn müəllimi + mərkəz (saxlayan çıxmaqla), bir dəfə.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.appeals.models import AppealDecisionRecord, AppealItem
from apps.appeals.services.teachers import subject_teachers, teaching_appeals_queryset
from apps.appeals.tests.test_key_correction_2026_10_13 import _AJAX, _KeyFixSetup
from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, ScheduleSlot
from core import runtime_settings
from core.rls import bypass_rls

User = get_user_model()
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _pdf(name="qerar.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class _ReviewSetup(_KeyFixSetup):
    def setUp(self):
        self._media = tempfile.mkdtemp(prefix="appeal-docs-")
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        media = override_settings(MEDIA_ROOT=self._media)
        media.enable()
        self.addCleanup(media.disable)
        super().setUp()
        with bypass_rls():
            self.subject_teacher = User.objects.create_user(
                "rt_subject", "rt_subject@qku.edu.az", "pw", first_name="Səbinə", last_name="Fənnova"
            )
            self.gone_teacher = User.objects.create_user(
                "rt_gone", "rt_gone@qku.edu.az", "pw", first_name="Köhnə", last_name="Müəllim"
            )
            self.other_teacher = User.objects.create_user("rt_other", "rt_other@qku.edu.az", "pw")
            for user in (self.subject_teacher, self.gone_teacher, self.other_teacher):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            self.offering = CourseOffering.objects.get(organization=self.org, subject=self.subject)
            self.offering.instructor = self.subject_teacher
            self.offering.save(update_fields=["instructor"])
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=1,
                start_time="09:00",
                end_time="10:20",
                instructor=self.gone_teacher,
            )
            # Slot müəllimi sonradan deaktiv edilib (işdən çıxıb) — «fənni tədris edən»-də görünməməlidir.
            User.objects.filter(pk=self.gone_teacher.pk).update(is_active=False)
        self.exam.subject = self.subject
        self.exam.save(update_fields=["subject"])
        from apps.appeals.models import Appeal

        self.appeal = Appeal.objects.get(pk=self.item.appeal_id)

    def _review_get(self, user=None):
        return self._client(user or self.head).get(
            reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1", **_AJAX
        )

    def _review_post(self, user=None, *, teacher="__default__", document=None, decision="accept"):
        data = {f"decision_{self.item.id}": decision, f"response_{self.item.id}": "Haqlıdır — dərslik 4.2."}
        if teacher == "__default__":
            data["decided_by_teacher"] = str(self.subject_teacher.pk)
        elif teacher is not None:
            data["decided_by_teacher"] = teacher
        if document is not None:
            data["decision_document"] = document
        with self.captureOnCommitCallbacks(execute=True):
            return self._client(user or self.head).post(
                reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1", data, **_AJAX
            )


class SubjectTeacherTests(_ReviewSetup):
    def test_teacher_computed_from_group_offering_and_inactive_excluded(self):
        self.assertEqual(subject_teachers(self.appeal), [self.subject_teacher])

    def test_falls_back_to_exam_author_when_no_offering_teacher(self):
        CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=None)
        ScheduleSlot.objects.filter(offering=self.offering).delete()
        self.appeal = AppealItem.objects.get(pk=self.item.pk).appeal
        self.assertEqual(subject_teachers(self.appeal), [self.teacher])

    def test_review_dialog_shows_subject_teacher_and_preselects_it(self):
        response = self._review_get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fənni tədris edən")
        self.assertContains(response, "Səbinə Fənnova")
        self.assertNotContains(response, "Köhnə Müəllim")
        self.assertContains(response, f'<option value="{self.subject_teacher.pk}" selected>', html=False)
        self.assertContains(response, f'<option value="{self.other_teacher.pk}">', html=False)
        self.assertContains(response, 'name="decision_document"', html=False)
        self.assertContains(response, 'data-live-search="true"', html=False)
        self.assertContains(response, "appeals/css/appeals/review_decider.css", html=False)

    def test_manage_list_shows_teacher_columns(self):
        self._review_post()
        response = self._client(self.head).get(reverse("appeals:manage_appeals") + "?fragment=1", **_AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qərarı verən müəllim")
        self.assertContains(response, "Səbinə Fənnova", count=2)

    def test_notification_link_deep_links_into_review_dialog(self):
        response = self._client(self.head).get(reverse("appeals:review_appeal", args=[self.appeal.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"open_appeal={self.appeal.id}", response["Location"])


class DecisionTeacherTests(_ReviewSetup):
    def test_teacher_required(self):
        response = self._review_post(teacher="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("müəllimi seçin", response.json()["error"])
        self.assertEqual(AppealItem.objects.get(pk=self.item.pk).status, "pending")
        self.assertFalse(AppealDecisionRecord.objects.exists())

    def test_student_or_foreign_user_rejected_as_teacher(self):
        for bad in (str(self.student.pk), str(self.gone_teacher.pk), "999999"):
            with self.subTest(bad=bad):
                self.assertEqual(self._review_post(teacher=bad).status_code, 400)

    def test_teacher_stored_with_saver_and_audited(self):
        response = self._review_post()
        self.assertEqual(response.status_code, 200, response.content)
        item = AppealItem.objects.get(pk=self.item.pk)
        self.assertEqual(item.decided_by_teacher, self.subject_teacher)
        self.assertEqual(item.resolved_by, self.head)
        record = AppealDecisionRecord.objects.get(appeal=self.appeal)
        self.assertEqual((record.decided_by_teacher, record.saved_by), (self.subject_teacher, self.head))
        self.assertEqual((record.accepted_count, record.rejected_count), (1, 0))
        self.assertLess(record.score_before, record.score_after)
        with bypass_rls():
            decision_row = AuditLog.objects.filter(resource_type="appeals.decision_record").latest("id")
            score_row = AuditLog.objects.filter(reason="Appeal accepted — score adjustment applied").latest("id")
        self.assertEqual(decision_row.new_values["decided_by_teacher_id"], self.subject_teacher.pk)
        self.assertEqual(decision_row.new_values["decided_by_teacher"], "Səbinə Fənnova")
        self.assertEqual(score_row.new_values["decided_by_teacher_id"], self.subject_teacher.pk)

    def test_teacher_shown_in_history_and_student_detail(self):
        self._review_post()
        history = self._review_get()
        self.assertContains(history, "qərarı verən müəllim: Səbinə Fənnova")
        # Tələbə nəticəni 5 dəqiqəlik redaktə pəncərəsindən sonra görür.
        AppealItem.objects.filter(pk=self.item.pk).update(resolved_at=timezone.now() - timedelta(minutes=10))
        detail = self._client(self.student).get(
            reverse("appeals:appeal_detail", args=[self.appeal.id]) + "?fragment=1", **_AJAX
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Qərarı verən")
        self.assertContains(detail, "Səbinə Fənnova")
        self.assertContains(detail, "data-appeal-comment-block", html=False)

    def test_missing_field_uses_single_subject_teacher(self):
        self.assertEqual(self._review_post(teacher=None).status_code, 200)
        self.assertEqual(AppealItem.objects.get(pk=self.item.pk).decided_by_teacher, self.subject_teacher)


class DecisionDocumentTests(_ReviewSetup):
    def test_document_optional_by_default(self):
        self.assertEqual(self._review_post().status_code, 200)
        self.assertFalse(AppealDecisionRecord.objects.get(appeal=self.appeal).document)

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_document_required_when_setting_on(self):
        from django.apps import apps

        runtime_settings.invalidate()
        self.addCleanup(runtime_settings.invalidate)
        apps.get_model("accounts", "RuntimeSetting").objects.create(key="exam.appeal_document_required", value=True)
        runtime_settings.invalidate()
        self.assertContains(self._review_get(), "data-required", html=False)
        response = self._review_post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("sənəd", response.json()["error"])
        self.assertEqual(AppealItem.objects.get(pk=self.item.pk).status, "pending")
        self.assertEqual(self._review_post(document=_pdf()).status_code, 200)
        record = AppealDecisionRecord.objects.get(appeal=self.appeal)
        self.assertTrue(record.document.name.startswith(f"appeal_documents/{self.org.id}/"))
        self.assertEqual(record.document_name, "qerar.pdf")

    def test_file_type_and_size_validated(self):
        bad_type = SimpleUploadedFile("x.exe", b"MZ\x90\x00binary", content_type="application/octet-stream")
        self.assertEqual(self._review_post(document=bad_type).status_code, 400)
        big = _pdf("big.pdf", PDF_BYTES + b"0" * (10 * 1024 * 1024 + 1))
        self.assertEqual(self._review_post(document=big).status_code, 400)
        self.assertFalse(AppealDecisionRecord.objects.exists())

    def test_download_only_for_appeal_staff(self):
        self.assertEqual(self._review_post(document=_pdf()).status_code, 200)
        record = AppealDecisionRecord.objects.get(appeal=self.appeal)
        url = reverse("protected_media", kwargs={"path": record.document.name})
        self.assertContains(self._review_get(), url, html=False)
        self.assertEqual(self._client(self.head).get(url).status_code, 200)
        self.assertEqual(self._client(self.reviewer).get(url).status_code, 200)  # superadmin
        for user in (self.student, self.subject_teacher, self.other_teacher):
            with self.subTest(user=user.username):
                self.assertIn(self._client(user).get(url).status_code, (403, 404))


class TeacherVisibilityTests(_ReviewSetup):
    def test_subject_teacher_sees_own_offering_appeals_only(self):
        self.assertIn(self.appeal, list(teaching_appeals_queryset(self.subject_teacher, self.org)))
        self.assertFalse(teaching_appeals_queryset(self.other_teacher, self.org).exists())
        # 2026-10-27: siyahı kabinet bölməsidir (``?section=teaching-appeals``) — köhnə URL ora yönləndirir.
        section = reverse("accounts:profile") + f"?section=teaching-appeals&ta_open={self.appeal.id}"
        page = self._client(self.subject_teacher).get(section)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.exam.title)
        self.assertContains(page, f'data-ta-open="{self.appeal.id}"', html=False)
        self.assertNotContains(page, "data-appeals-review-form", html=False)  # qərar hüququ yoxdur
        other = self._client(self.other_teacher).get(reverse("accounts:profile") + "?section=teaching-appeals")
        self.assertNotContains(other, self.exam.title)

    def test_teacher_still_cannot_decide(self):
        response = self._review_post(user=self.subject_teacher)
        self.assertIn(response.status_code, (403,))
        self.assertEqual(AppealItem.objects.get(pk=self.item.pk).status, "pending")

    def test_rim_head_sees_all_in_manage_list(self):
        response = self._client(self.head).get(reverse("appeals:manage_appeals") + "?fragment=1", **_AJAX)
        self.assertContains(response, self.exam.title)
        self.assertContains(response, "Fənni tədris edən")


class NotificationTests(_ReviewSetup):
    def test_filing_notifies_subject_teacher_and_center_once(self):
        marker = {"metadata__appeal_id": self.appeal.id}
        # Müraciət setUp-da (açılış müəllimi təyin edilməzdən ƏVVƏL) yaradılıb → yenisini yaradaq.
        from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
        from apps.appeals.services import create_appeal

        appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[{"question_id": self.q2.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": "x" * 40}],
        )
        marker = {"metadata__appeal_id": appeal.id}
        self.assertEqual(InAppNotification.objects.filter(recipient=self.subject_teacher, **marker).count(), 1)
        self.assertEqual(InAppNotification.objects.filter(recipient=self.head, **marker).count(), 1)
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_teacher, **marker).exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.gone_teacher, **marker).exists())

    def test_decision_notifies_teacher_and_center_once_with_teacher_and_score(self):
        superhead = User.objects.create_user("rt_head2", "rt_head2@qku.edu.az", "pw")
        Membership.objects.create(
            user=superhead,
            organization=self.org,
            role=self.org.roles.get(name="exam_center_head"),
            is_active=True,
        )
        self.assertEqual(self._review_post().status_code, 200)
        marker = {"metadata__appeal_id": self.appeal.id, "title": "Apellyasiya qərarı verildi"}
        teacher_notes = InAppNotification.objects.filter(recipient=self.subject_teacher, **marker)
        self.assertEqual(teacher_notes.count(), 1)
        self.assertIn("Qərarı verən müəllim: Səbinə Fənnova", teacher_notes.get().message)
        self.assertIn("→", teacher_notes.get().message)
        self.assertIn("section=teaching-appeals", unquote(teacher_notes.get().link))
        center_notes = InAppNotification.objects.filter(recipient=superhead, **marker)
        self.assertEqual(center_notes.count(), 1)
        self.assertIn(reverse("appeals:review_appeal", args=[self.appeal.id]), unquote(center_notes.get().link))
        # Saxlayan özü almır; köhnə «bal dəyişdi» bildirişi eyni hadisədə təkrarlanmır.
        self.assertFalse(InAppNotification.objects.filter(recipient=self.head, **marker).exists())
        self.assertFalse(
            InAppNotification.objects.filter(
                recipient=self.teacher, title="Apellyasiya nəticəsində bal dəyişdi", metadata__appeal_id=self.appeal.id
            ).exists()
        )
