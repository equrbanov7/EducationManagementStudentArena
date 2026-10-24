"""25% paketinin rəy düzəlişləri (2026-10-18) — HIGH-1/2, MEDIUM-3/4, LOW-5/9/10 reqressiyaları.

Onlayn 25% cəhdi: «İmtahan şansı ver» (səbəb «25% müraciəti») qeydindən SONRA başlanmış cəhdin balı imtahan
körpüsündən (``exam_bridge.record_exam_result(attempt=…)``) keçir. Əsas imtahanın balı ``FinalGrade``-də qalır.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Membership, Organization
from apps.registrar import exam_bridge, retake_chance, retake_decisions, retake_queries, retake_services, retake_views
from apps.registrar.models import (
    FinalGrade,
    ResitRecord,
    RetakeApplication,
    RetakeEventAction,
    RetakeReceipt,
    RetakeStatus,
)
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf

User = get_user_model()
PROFILE = "/accounts/profile/"


class OnlineRetakeAttemptTest(RetakeBase):
    """Rəyçinin probları: HIGH-1, HIGH-2, MEDIUM-3."""

    def setUp(self):
        self.fail_exam(score=12)  # əsas imtahan 12 / 50
        now = timezone.now()
        with bypass_rls():
            self.exam = Exam.objects.create(
                title="INF101 yekun",
                author=self.teacher,
                organization=self.org,
                subject=self.subject,
                exam_type="test",
                exam_type_extended="final",
                is_active=True,
                is_public=False,
                max_attempts_per_user=1,
                total_duration_minutes=60,
                start_datetime=now - timedelta(hours=1),
                end_datetime=now + timedelta(hours=3),
            )
            self.original_attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                status="submitted",
                attempt_number=1,
                started_at=now - timedelta(days=30),
                finished_at=now - timedelta(days=30),
            )
            ExamAttempt.objects.filter(pk=self.original_attempt.pk).update(started_at=now - timedelta(days=30))
            self.original_attempt.refresh_from_db()

    def _granted(self):
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount="100"
            )
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            exam = {
                "id": self.exam.pk,
                "title": self.exam.title,
                "exam_type": "test",
                "category": "final",
                "subject_id": self.subject.id,
            }
            cleaned = retake_chance.validate(
                organization=self.org, exam=exam, students=[self.student], reason="retake_25", document=pdf("emr.pdf")
            )
            retake_chance.record(
                organization=self.org, exam=exam, students=[self.student], cleaned=cleaned, extra=1, actor=self.dean
            )
            attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                status="submitted",
                attempt_number=2,
                started_at=timezone.now() + timedelta(seconds=1),
                finished_at=timezone.now() + timedelta(minutes=50),
            )
        return app, attempt

    def _sync(self, attempt, percent):
        with bypass_rls():
            return exam_bridge.record_exam_result(
                student=self.student,
                subject_id=self.subject.id,
                organization=self.org,
                score_percent=percent,
                attempt=attempt,
            )

    def _original_score(self):
        return FinalGrade.objects.get(enrollment=self.enrollment).exam_score

    def test_original_attempt_regrade_does_not_touch_admitted_application(self):
        """HIGH-1: əsas cəhdin yenidən yoxlanması (12 → 14) müraciəti tamamlamır, ResitRecord-a toxunmur."""
        app, _attempt = self._granted()
        self._sync(self.original_attempt, 28)  # 28% → 14 / 50
        with bypass_rls():
            app.refresh_from_db()
            resit = ResitRecord.objects.filter(enrollment=self.enrollment).first()
            self.assertEqual(self._original_score(), Decimal("14"))
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)
        self.assertTrue(resit is None or resit.resit_score is None)

    def test_later_regrade_of_retake_attempt_reaches_final_result(self):
        """HIGH-2: 25% nəticəsi 20, sonra yoxlama 45 → ResitRecord 45, yekun 45; əsas bal FinalGrade-də 12 qalır."""
        app, attempt = self._granted()
        self._sync(attempt, 40)  # 20 / 50
        with bypass_rls():
            app.refresh_from_db()
            self.assertEqual((app.status, app.result_score), (RetakeStatus.COMPLETED, Decimal("20")))
        self._sync(attempt, 90)  # 45 / 50
        from apps.registrar import finals

        with bypass_rls():
            app.refresh_from_db()
            resit = ResitRecord.objects.get(enrollment=self.enrollment)
            result = finals.compute_final_result(enrollment=self.enrollment)
            recorded = app.events.filter(action=RetakeEventAction.RESULT_RECORDED).count()
            lines = retake_queries.result_lines(organization=self.org, enrollment_ids=[self.enrollment.id])
            original = self._original_score()
        self.assertEqual(resit.resit_score, Decimal("45"))
        self.assertEqual(app.result_score, Decimal("45"))
        self.assertEqual(result["effective_exam"], Decimal("45"))
        self.assertEqual(recorded, 2)
        self.assertEqual(original, Decimal("12"))  # «əvvəlki nəticə» qalır
        self.assertEqual(lines[self.enrollment.id]["text"], "Əsas imtahan: 12 → 25%: 45")

    def test_retake_equal_to_original_still_completes(self):
        """MEDIUM-3: əsas 12, 25% də 12 → müraciət tamamlanır (köhnə ≠ yeni şərti yoxdur)."""
        app, attempt = self._granted()
        self._sync(attempt, 24)  # 12 / 50
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.COMPLETED)
        self.assertEqual(app.result_score, Decimal("12"))

    def test_attempt_before_grant_is_not_a_retake(self):
        app, _attempt = self._granted()
        with bypass_rls():
            early = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                status="submitted",
                attempt_number=3,
                started_at=timezone.now() - timedelta(days=1),
                finished_at=timezone.now() - timedelta(days=1),
            )
            # ``started_at`` auto_now_add-dır — keçmişə update() ilə çəkilir.
            ExamAttempt.objects.filter(pk=early.pk).update(started_at=timezone.now() - timedelta(days=1))
            early.refresh_from_db()
        self._sync(early, 60)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)


@override_settings(UNIVERSITY_MODE=True)
class ReviewHttpTest(RetakeBase):
    def setUp(self):
        self.fail_exam()

    def test_view_as_blocks_every_write(self):
        """MEDIUM-4: view-as rejimində bütün POST-lar 403 + view_as_blocked."""
        factory = RequestFactory()
        views = [
            (retake_views.apply, ()),
            (retake_views.upload_receipt, ("00000000-0000-0000-0000-000000000001",)),
            (retake_views.withdraw, ("00000000-0000-0000-0000-000000000001",)),
            (retake_views.payment, ("00000000-0000-0000-0000-000000000001",)),
            (retake_views.decision, ("00000000-0000-0000-0000-000000000001",)),
            (retake_views.result, ("00000000-0000-0000-0000-000000000001",)),
        ]
        for view, args in views:
            request = factory.post("/x/", {"kind": "retake_25"})
            request.user = self.dean
            request.is_view_as = True
            response = view(request, *args)
            self.assertEqual(response.status_code, 403, view.__name__)
            self.assertIn(b"view_as_blocked", response.content)

    def test_trail_does_not_leak_other_organisation_users(self):
        """LOW-5: org-geniş açar başqa təşkilatın istifadəçisinin izini (adını) açmır → 404."""
        boss = self._staff("rt_boss", ["retake.manage"], RoleScopeType.ORGANIZATION)
        stranger_owner = User.objects.create_user("rt_x_owner", "rt_x_owner@qku.edu.az", "pw")
        with bypass_rls():
            other = Organization.objects.create(
                name="Other Univ",
                slug="rt-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=stranger_owner,
                status="active",
                is_active=True,
            )
            stranger = User.objects.create_user("rt_stranger", "rt_stranger@qku.edu.az", "pw")
            Membership.objects.create(
                user=stranger, organization=other, role=other.roles.get(name="student"), is_primary=True, is_active=True
            )
        client = self.client_for(boss)
        self.assertEqual(client.get(reverse("retake:trail", args=[stranger.pk])).status_code, 404)
        body = client.get(f"{PROFILE}?section=retake-desk&rt_tab=all&rt_student={stranger.pk}").content.decode()
        self.assertNotIn("rt_stranger", body)
        self.assertEqual(client.get(reverse("retake:trail", args=[self.student.pk])).status_code, 200)

    def test_exam_centre_records_paper_result_from_desk(self):
        """HIGH-1 qeydi: kağız / praktiki 25% yalnız desk «Nəticə» ilə — İmtahan mərkəzi `final_score.entry` ilə yazır."""
        center = self._staff("rt_center2", ["final_score.entry"], RoleScopeType.ORGANIZATION)
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=app.id, paid_amount="100"
            )
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
        client = self.client_for(center)
        too_high = client.post(reverse("retake:result", args=[app.id]), {"score": "61"})
        self.assertEqual(too_high.status_code, 400)
        self.assertIn("50", too_high.json()["error"])
        ok = client.post(reverse("retake:result", args=[app.id]), {"score": "38"})
        self.assertEqual(ok.status_code, 200, ok.content)
        with bypass_rls():
            app.refresh_from_db()
        self.assertEqual((app.status, app.result_score), (RetakeStatus.COMPLETED, Decimal("38")))

    def test_rolled_back_upload_leaves_no_file(self):
        """LOW-9: tranzaksiya geri qayıdanda yazılmış qəbz faylı silinir."""
        from django.core.files.storage import default_storage

        saved = []
        original_track = retake_services.retake_files.track

        def spy(field_file):
            saved.append(field_file.name)
            original_track(field_file)

        with (
            bypass_rls(),
            mock.patch.object(retake_services.retake_files, "track", spy),
            mock.patch.object(retake_services, "transition", side_effect=ValidationError("boom")),
        ):
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student,
                    organization=self.org,
                    enrollment_id=self.enrollment.id,
                    kind="retake_25",
                    receipt=pdf(),
                )
        self.assertTrue(saved)
        self.assertFalse(default_storage.exists(saved[0]))
        self.assertFalse(RetakeReceipt.objects.exists())
        self.assertFalse(RetakeApplication.objects.exists())

    def test_unit_scoped_notifications_reach_only_covering_dean(self):
        """LOW-8: fakültə B dekanı fakültə A tələbəsinin müraciəti üçün bildiriş almır."""
        from apps.registrar import retake_notify

        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            recipients = {u.username for u in retake_notify._key_holders(app, "retake.manage")}
            accounting = {u.username for u in retake_notify._key_holders(app, "retake.payment_verify")}
        self.assertIn("rt_dean", recipients)
        self.assertNotIn("rt_dean_b", recipients)
        self.assertEqual(accounting, {"rt_acc"})


@override_settings(UNIVERSITY_MODE=True)
class LegacyGrantHistoryTest(RetakeBase):
    def test_legacy_attempt_grants_stay_visible(self):
        """LOW-10: «İmtahan şansı ver» köhnə StudentExamAttemptGrant sətirlərini itirmir (KPI + siyahı)."""
        from apps.exams.models import StudentExamAttemptGrant
        from apps.exams.tests.test_exam_center_policy import _assign_user_to_org

        center = User.objects.create_user("rt_center3", "rt_center3@qku.edu.az", "pw")
        _assign_user_to_org(center, self.org, ProfileRole.MEMBER, "exam_center_head")
        now = timezone.now()
        exam = Exam.objects.create(
            title="Köhnə final",
            author=center,
            organization=self.org,
            subject=self.subject,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            max_attempts_per_user=1,
            total_duration_minutes=60,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=1),
        )
        StudentExamAttemptGrant.objects.create(exam=exam, student=self.other, extra_attempts=2, granted_by=center)
        body = self.client_for(center).get(f"{PROFILE}?section=exam-chance").content.decode()
        self.assertIn("Köhnə qeyd", body)
        self.assertIn("rt_other", body)
        from apps.accounts.views.profile._sections.exam_chance import _legacy_grants

        legacy = _legacy_grants(self.org)
        self.assertEqual((legacy["count"], legacy["attempts"], legacy["new_students"]), (1, 2, 1))
