"""KAFEDRA TƏSDİQİ halqasının testləri (müəllim → kafedra müdiri → mərkəz).

Əhatə:

* marşrut: göndəriş kafedraya düşür, kafedra müdirinə bildiriş gedir, mərkəz
  hələ HEÇ NƏ görmür;
* vəziyyət maşını: qanunsuz keçidlər (mərkəzin təsdiqsiz qərarı, müəllimin
  kafedranı atlaması) bloklanır;
* icazə mənfiləri: başqa kafedranın müdiri 403, mərkəz təsdiqdən əvvəl 403;
* dekanlıq fallback-ı: kafedra müdiri yoxdursa göndəriş dekanlığa gedir;
* audit + bildiriş alıcıları + hadisə lentı;
* bölmə görünürlüyü və sidebar badge sayğacı.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import QuestionSubmission, QuestionSubmissionEvent
from apps.exams.services.question_chair_review import (
    chair_approve,
    chair_reject,
    chair_request_revision,
    pending_chair_review_count,
)
from apps.exams.services.question_submission import (
    accept_submission,
    ensure_can_review_submission,
    resubmit_question_set,
    submit_question_set,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()

VALID_TEXT = (
    "1. Azərbaycanın paytaxtı hansıdır?\n"
    "*A) Bakı\n"
    "B) Gəncə\n"
    "C) Sumqayıt\n"
    "D) Şəki\n"
    "E) Lənkəran\n"
    "2. 2 + 2 neçə edir?\n"
    "A) 3\n"
    "*B) 4\n"
    "C) 5\n"
    "D) 6\n"
    "E) 7\n"
)

LONG_REASON = "3-cü sualda düzgün cavab işarələnməyib, 5-ci sual mövzudan kənardır."


class _ChairBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("qc_owner", "qc_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="QC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(organization=cls.org, name="QC fakültəsi", unit_type=OrgUnitType.FACULTY)
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, name="QC informatika kafedrası", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
        )
        cls.other_chair = OrgUnit.objects.create(
            organization=cls.org, name="QC fizika kafedrası", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
        )
        # Müdiri OLMAYAN kafedra — dekanlıq fallback-ı üçün.
        cls.orphan_chair = OrgUnit.objects.create(
            organization=cls.org, name="QC kimya kafedrası", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
        )

        cls.teacher = cls._member("qc_teacher", ProfileRole.TEACHER, "teacher", cls.chair)
        cls.orphan_teacher = cls._member("qc_teacher2", ProfileRole.TEACHER, "teacher", cls.orphan_chair)
        cls.chair_head = cls._member("qc_chair", ProfileRole.MEMBER, "chair_head", cls.chair)
        cls.other_chair_head = cls._member("qc_chair2", ProfileRole.MEMBER, "chair_head", cls.other_chair)
        cls.dean = cls._member("qc_dean", ProfileRole.MEMBER, "dean", cls.faculty)
        cls.exam_center = cls._member("qc_center", ProfileRole.MEMBER, "exam_center", None)

    @classmethod
    def _member(cls, username, profile_role, role_name, scope_unit):
        user = User.objects.create_user(username, f"{username}@test.az", PASSWORD)
        _assign_user_to_org(user, cls.org, profile_role, role_name)
        if scope_unit is not None:
            Membership.objects.filter(user=user, organization=cls.org).update(scope_unit=scope_unit)
        return user

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _submit(self, teacher=None, title="Kafedra testi", exam_kind="midterm"):
        return submit_question_set(
            teacher=teacher or self.teacher,
            organization=self.org,
            title=title,
            subject="İnformatika",
            group_label="875i",
            language="az",
            raw_text=VALID_TEXT,
            exam_kind=exam_kind,
        )


class ChairRoutingTests(_ChairBase):
    def test_submission_lands_at_chair_not_center(self):
        submission = self._submit()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertEqual(submission.chair_unit, self.chair)
        self.assertFalse(submission.routed_to_dean)
        self.assertIsNone(submission.reached_center_at)
        self.assertFalse(submission.has_reached_center)

    def test_submission_creates_append_only_event(self):
        submission = self._submit()
        events = list(submission.events.all())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, QuestionSubmissionEvent.ACTION_SUBMITTED_TO_CHAIR)
        self.assertEqual(events[0].to_status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertEqual(events[0].actor, self.teacher)

    def test_chair_head_notified_center_is_not(self):
        self._submit()
        self.assertTrue(InAppNotification.objects.filter(recipient=self.chair_head).exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.exam_center).exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_chair_head).exists())

    def test_missing_chair_head_routes_to_dean(self):
        submission = self._submit(teacher=self.orphan_teacher, title="Sahibsiz kafedra")
        self.assertTrue(submission.routed_to_dean)
        self.assertEqual(submission.chair_unit, self.orphan_chair)
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertTrue(InAppNotification.objects.filter(recipient=self.dean).exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.exam_center).exists())


class ChairDecisionTests(_ChairBase):
    def test_approve_moves_to_center_and_notifies(self):
        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_APPROVED)
        self.assertIsNotNone(submission.reached_center_at)
        self.assertEqual(submission.chair_reviewer, self.chair_head)
        self.assertEqual(submission.chair_decision, QuestionSubmission.CHAIR_DECISION_APPROVED)
        self.assertTrue(InAppNotification.objects.filter(recipient=self.exam_center).exists())
        self.assertTrue(InAppNotification.objects.filter(recipient=self.teacher).exists())

    def test_approve_writes_audit_row(self):
        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.chair_head,
                resource_type="question_submission",
                resource_id=str(submission.pk),
            ).exists()
        )

    def test_revision_requires_long_reason(self):
        submission = self._submit()
        with self.assertRaises(ValidationError):
            chair_request_revision(submission, actor=self.chair_head, reason="qısa")
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)

    def test_revision_sets_status_and_reason(self):
        submission = self._submit()
        chair_request_revision(submission, actor=self.chair_head, reason=LONG_REASON)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_REVISION)
        self.assertEqual(submission.chair_note, LONG_REASON)
        event = submission.events.filter(action=QuestionSubmissionEvent.ACTION_CHAIR_REVISION).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.reason, LONG_REASON)

    def test_reject_never_reaches_center(self):
        submission = self._submit()
        chair_reject(submission, actor=self.chair_head, reason=LONG_REASON)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_REJECTED)
        self.assertIsNone(submission.reached_center_at)
        with self.assertRaises(PermissionDenied):
            ensure_can_review_submission(self.exam_center, submission)

    def test_double_decision_blocked(self):
        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        submission.refresh_from_db()
        with self.assertRaises(ValidationError):
            chair_approve(submission, actor=self.chair_head)

    def test_dean_decides_only_on_fallback(self):
        fallback = self._submit(teacher=self.orphan_teacher, title="Dekan qərarı")
        chair_approve(fallback, actor=self.dean)
        fallback.refresh_from_db()
        self.assertEqual(fallback.status, QuestionSubmission.STATUS_CHAIR_APPROVED)

        # Kafedra müdiri OLAN göndərişə dekan qərar VERƏ BİLMİR.
        owned = self._submit(title="Kafedralı göndəriş")
        with self.assertRaises(PermissionDenied):
            chair_approve(owned, actor=self.dean)


class ChairPermissionTests(_ChairBase):
    def test_other_chair_head_gets_403(self):
        submission = self._submit()
        with self.assertRaises(PermissionDenied):
            chair_approve(submission, actor=self.other_chair_head)
        response = self._client_for(self.other_chair_head).get(
            reverse("exams:question_submission_chair_review", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_open_chair_review(self):
        submission = self._submit()
        response = self._client_for(self.teacher).get(
            reverse("exams:question_submission_chair_review", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_center_cannot_act_before_chair_approval(self):
        submission = self._submit()
        with self.assertRaises(PermissionDenied):
            ensure_can_review_submission(self.exam_center, submission)
        with self.assertRaises(ValidationError):
            accept_submission(submission, reviewer=self.exam_center, new_bank_name="Erkən bank")

        client = self._client_for(self.exam_center)
        review_url = reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        self.assertEqual(client.get(review_url).status_code, 403)
        # Detal səthində də görünmür (mövcudluq sızması yoxdur).
        detail_url = reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})
        self.assertEqual(client.get(detail_url).status_code, 404)

    def test_center_can_act_after_chair_approval(self):
        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        submission.refresh_from_db()
        client = self._client_for(self.exam_center)
        review_url = reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        self.assertEqual(client.get(review_url).status_code, 200)
        submission.refresh_from_db()
        # Səhifənin açılması izə düşür (chair_approved → center_review).
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CENTER_REVIEW)
        self.assertTrue(submission.events.filter(action=QuestionSubmissionEvent.ACTION_CENTER_OPENED).exists())

    def test_chair_decide_via_view_requires_reason(self):
        submission = self._submit()
        client = self._client_for(self.chair_head)
        url = reverse("exams:question_submission_chair_decide", kwargs={"submission_id": submission.id})
        client.post(url, {"decision": "reject", "reason": "yox"})
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)

        client.post(url, {"decision": "approve", "reason": ""})
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_APPROVED)


class ChairCycleTests(_ChairBase):
    def test_teacher_cannot_skip_chair_on_resubmit(self):
        submission = self._submit()
        chair_request_revision(submission, actor=self.chair_head, reason=LONG_REASON)
        submission.refresh_from_db()
        resubmit_question_set(submission, raw_text=VALID_TEXT)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertIsNone(submission.reached_center_at)
        self.assertEqual(submission.resubmission_count, 1)
        self.assertEqual(submission.chair_decision, "")
        actions = list(submission.events.values_list("action", flat=True))
        self.assertEqual(
            actions,
            [
                QuestionSubmissionEvent.ACTION_SUBMITTED_TO_CHAIR,
                QuestionSubmissionEvent.ACTION_CHAIR_REVISION,
                QuestionSubmissionEvent.ACTION_RESUBMITTED_TO_CHAIR,
            ],
        )

    def test_center_revision_returns_through_chair(self):
        from apps.exams.services.question_submission import request_center_revision

        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        submission.refresh_from_db()
        request_center_revision(submission, reviewer=self.exam_center, note=LONG_REASON)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CENTER_REVISION)

        resubmit_question_set(submission, raw_text=VALID_TEXT)
        submission.refresh_from_db()
        # Mərkəzin düzəlişindən sonra dəst YENİDƏN kafedradan keçir.
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertIsNone(submission.reached_center_at)


class ChairQueueAndSectionTests(_ChairBase):
    def test_queue_scoped_to_own_chair(self):
        mine = self._submit(title="Mənim kafedram")
        self._submit(teacher=self.orphan_teacher, title="Başqa kafedra")
        client = self._client_for(self.chair_head)
        response = client.get(f"{reverse('accounts:profile')}?section=question-chair-review")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mənim kafedram")
        self.assertNotContains(response, "Başqa kafedra")
        self.assertEqual(pending_chair_review_count(self.chair_head, self.org), 1)
        self.assertEqual(mine.chair_unit, self.chair)

    def test_badge_count_drops_after_approval(self):
        submission = self._submit()
        self.assertEqual(pending_chair_review_count(self.chair_head, self.org), 1)
        chair_approve(submission, actor=self.chair_head)
        self.assertEqual(pending_chair_review_count(self.chair_head, self.org), 0)

    def test_section_visibility_per_role(self):
        sidebar_url = reverse("accounts:profile")
        chair_response = self._client_for(self.chair_head).get(sidebar_url)
        self.assertContains(chair_response, "section=question-chair-review")

        for user in (self.teacher, self.exam_center):
            response = self._client_for(user).get(sidebar_url)
            self.assertNotContains(response, "section=question-chair-review")

    def test_teacher_section_denied_for_chair_queue(self):
        response = self._client_for(self.teacher).get(f"{reverse('accounts:profile')}?section=question-chair-review")
        self.assertNotContains(response, 'data-profile-section-panel="question-chair-review"', status_code=200)


class ChairEventLedgerImmutabilityTests(_ChairBase):
    """Hadisə lentı ƏLAVƏ-ONLY-dir — UPDATE DB səviyyəsində bloklanır.

    Audit 2026-09-03 (Wave 2): model docstring-i «redaktə/silmə YOXDUR» deyirdi,
    amma qayda yalnız servis qatının nizamı idi. Trigger
    ``exams/migrations/0065`` ilə gəldi.
    """

    def test_raw_update_on_the_event_ledger_is_rejected(self):
        from django.db import connection, transaction
        from django.db.utils import InternalError, ProgrammingError

        if connection.vendor != "postgresql":
            self.skipTest("Append-only trigger yalnız PostgreSQL-dədir.")

        submission = self._submit()
        chair_approve(submission, actor=self.chair_head)
        event = QuestionSubmissionEvent.objects.filter(
            submission=submission, action=QuestionSubmissionEvent.ACTION_CHAIR_APPROVED
        ).first()
        self.assertIsNotNone(event)

        with self.assertRaises((InternalError, ProgrammingError)):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE exams_questionsubmissionevent SET reason = %s WHERE id = %s",
                    ["silinmiş iz", event.pk],
                )

        event.refresh_from_db()
        self.assertNotEqual(event.reason, "silinmiş iz")
