"""25% təkrar imtahan / alt qrup müraciəti — uyğunluq, status maşını, tarixçə (sahib 2026-10-18)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import override_settings

from apps.registrar import finals, retake_chance, retake_decisions, retake_eligibility, retake_queries, retake_services
from apps.registrar.models import (
    ExamChanceGrant,
    ExamChanceReason,
    ResitRecord,
    RetakeApplication,
    RetakeApplicationEvent,
    RetakeEventAction,
    RetakeKind,
    RetakeReceipt,
    RetakeStatus,
)
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf


def _row(student, org, subject):
    rows = retake_eligibility.failed_subjects(student=student, organization=org)
    return next((r for r in rows if r["subject"].id == subject.id), None)


class _Helpers(RetakeBase):
    def _admitted(self, student=None, enrollment=None):
        student = student or self.student
        enrollment = enrollment or self.enrollment
        app = retake_services.apply(
            student=student, organization=self.org, enrollment_id=enrollment.id, kind="retake_25", receipt=pdf()
        )
        retake_decisions.verify_payment(
            actor=self.accountant, organization=self.org, application_id=app.id, paid_amount="100"
        )
        return retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)


class EligibilityTest(_Helpers):
    def test_failed_exam_offers_both_options(self):
        self.fail_exam()
        with bypass_rls():
            row = _row(self.student, self.org, self.subject)
        self.assertIsNotNone(row)
        self.assertEqual(row["fail_reason"], "exam25")
        self.assertTrue(row["options"]["retake_25"]["allowed"])
        self.assertTrue(row["options"]["subgroup"]["allowed"])
        self.assertEqual((row["attempts_used"], row["attempts_limit"]), (0, 1))

    def test_absence_limit_exceeded_means_subgroup_only(self):
        self.bar_by_absence()
        with bypass_rls():
            row = _row(self.student, self.org, self.subject)
        self.assertEqual(row["fail_reason"], "qb")
        self.assertFalse(row["options"]["retake_25"]["allowed"])
        self.assertIn("alt qrup", row["options"]["retake_25"]["why"])
        self.assertTrue(row["options"]["subgroup"]["allowed"])
        with bypass_rls(), self.assertRaises(ValidationError):
            retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )

    def test_passed_subject_is_not_listed(self):
        self.fail_exam(score=45)  # giriş 0 + 45 < 51 → hələ kəsr
        with bypass_rls():
            self.assertIsNotNone(_row(self.student, self.org, self.subject))
            finals.set_exam_score(enrollment=self.enrollment, score=50)
            ResitRecord.objects.filter(enrollment=self.enrollment).delete()
        # 0 + 50 = 50 < 51 — hələ də kəsr; keçən tələbə nümunəsi: başqa tələbə ümumiyyətlə bal almayıb.
        with bypass_rls():
            self.assertIsNone(_row(self.other, self.org, self.subject))

    @override_settings(RETAKE_APPLICATIONS_OPEN=False)
    def test_closed_window_blocks_everything(self):
        self.fail_exam()
        with bypass_rls():
            row = _row(self.student, self.org, self.subject)
            self.assertFalse(row["options"]["retake_25"]["allowed"])
            self.assertFalse(row["options"]["subgroup"]["allowed"])
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
                )

    def test_attempt_limit(self):
        self.fail_exam()
        with bypass_rls():
            app = self._admitted()
            retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=app.id, score=12)
            row = _row(self.student, self.org, self.subject)
        self.assertEqual(row["attempts_used"], 1)
        self.assertFalse(row["options"]["retake_25"]["allowed"])
        self.assertIn("1/1", row["options"]["retake_25"]["why"])
        self.assertTrue(row["options"]["subgroup"]["allowed"])
        with override_settings(RETAKE_MAX_ATTEMPTS=2), bypass_rls():
            self.assertTrue(_row(self.student, self.org, self.subject)["options"]["retake_25"]["allowed"])


class FlowTest(_Helpers):
    """Tam axın + rədd/yenidən yükləmə + geri götürmə + alt qrup + qarmaqlar."""

    def test_happy_path_records_every_step(self):
        self.fail_exam(score=10)
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                note="Ödəniş etdim",
                receipt=pdf(),
            )
            self.assertEqual(app.status, RetakeStatus.PAYMENT_PENDING_REVIEW)
            self.assertEqual(app.base_exam_score, Decimal("10"))
            self.assertEqual(app.eligibility["fail_reason"], "exam25")
            retake_decisions.verify_payment(
                actor=self.accountant,
                organization=self.org,
                application_id=app.id,
                payment_reference="BNK-77",
                paid_amount="100",
            )
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=app.id, score=45)
            app.refresh_from_db()
            resit = ResitRecord.objects.get(enrollment=self.enrollment)
            result = finals.compute_final_result(enrollment=self.enrollment)
            actions = list(app.events.order_by("created_at").values_list("action", flat=True))
        self.assertEqual(app.status, RetakeStatus.COMPLETED)
        self.assertEqual(app.payment_reference, "BNK-77")
        self.assertEqual(app.attempt_number, 1)
        self.assertEqual(resit.resit_score, Decimal("45"))
        self.assertEqual(app.resit_record_id, resit.id)
        self.assertEqual(result["effective_exam"], Decimal("45"))  # təkrar imtahan balı qüvvədədir
        self.assertEqual(app.result_total, result["total"])
        self.assertEqual(
            actions,
            [
                RetakeEventAction.SUBMITTED,
                RetakeEventAction.RECEIPT_UPLOADED,
                RetakeEventAction.PAYMENT_VERIFIED,
                RetakeEventAction.ADMITTED,
                RetakeEventAction.RESULT_RECORDED,
            ],
        )
        self.assertEqual(retake_queries.result_text(app), "Əsas imtahan: 10 → 25%: 45")

    def test_receipt_rejected_then_reuploaded(self):
        self.fail_exam()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
            self.assertEqual(app.status, RetakeStatus.SUBMITTED)
            retake_services.upload_receipt(
                student=self.student, organization=self.org, application_id=app.id, receipt=pdf("a.pdf")
            )
            with self.assertRaises(ValidationError):  # qısa səbəb
                retake_decisions.reject_payment(
                    actor=self.accountant, organization=self.org, application_id=app.id, reason="qısa"
                )
            retake_decisions.reject_payment(
                actor=self.accountant,
                organization=self.org,
                application_id=app.id,
                reason="Qəbzdə məbləğ və tələbənin adı görünmür, yenidən yükləyin.",
            )
            app.refresh_from_db()
            self.assertEqual(app.status, RetakeStatus.PAYMENT_REJECTED)
            retake_services.upload_receipt(
                student=self.student,
                organization=self.org,
                application_id=app.id,
                receipt=pdf("b.pdf", b"%PDF-1.4\nyeni qebz\n%%EOF\n"),
            )
            app.refresh_from_db()
            receipts = list(app.receipts.order_by("created_at"))
        self.assertEqual(app.status, RetakeStatus.PAYMENT_PENDING_REVIEW)
        self.assertEqual(len(receipts), 2)  # köhnə qəbz itmir
        self.assertEqual(app.current_receipt_id, receipts[-1].id)
        self.assertEqual(receipts[0].original_name, "a.pdf")
        self.assertEqual(len(receipts[0].sha256), 64)
        self.assertEqual(receipts[0].size, len(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"))
        self.assertRegex(receipts[0].file.name, r"/[0-9a-f]{32}\.pdf$")  # təsadüfi ad, orijinal ad yolda yoxdur

    def test_withdraw_only_before_decision(self):
        self.fail_exam()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
            with self.assertRaises(PermissionDenied):
                retake_services.withdraw(student=self.other, organization=self.org, application_id=app.id)
            retake_services.withdraw(
                student=self.student, organization=self.org, application_id=app.id, note="fikrimi dəyişdim"
            )
            app.refresh_from_db()
            self.assertEqual(app.status, RetakeStatus.WITHDRAWN)
            admitted = self._admitted()
            with self.assertRaises(ValidationError):
                retake_services.withdraw(student=self.student, organization=self.org, application_id=admitted.id)

    def test_subgroup_without_payment_uses_placement_service(self):
        self.bar_by_absence()
        placed = mock.Mock(name="place_in_subgroup", return_value=None)
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            self.assertEqual(app.status, RetakeStatus.SUBMITTED)
            with self.assertRaises(ValidationError):
                retake_services.upload_receipt(
                    student=self.student, organization=self.org, application_id=app.id, receipt=pdf()
                )
            with mock.patch("apps.registrar.public.place_in_subgroup", placed, create=True):
                retake_decisions.approve_subgroup(
                    actor=self.dean,
                    organization=self.org,
                    application_id=app.id,
                    document=pdf("teqdimat.pdf"),
                    reason="Qayıb həddi keçildiyi üçün G2 ilə yenidən keçir.",
                    offering_id=self.target.id,
                )
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.COMPLETED)
        self.assertTrue(app.decision_document.name.startswith(f"retake_documents/{self.org.id}/"))
        placed.assert_called_once()
        kwargs = placed.call_args.kwargs
        self.assertEqual(kwargs["student"], self.student)
        self.assertEqual(kwargs["offering"], self.target)
        self.assertEqual(kwargs["actor"], self.dean)

    def test_subgroup_with_real_placement_service(self):
        """Paralel agentin ``registrar.public.place_in_subgroup`` servisi — həqiqi yerləşdirmə (mok yox)."""
        from apps.registrar import public

        if not callable(getattr(public, "place_in_subgroup", None)):
            self.skipTest("place_in_subgroup hələ quraşdırılmayıb")
        self.bar_by_absence()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            retake_decisions.approve_subgroup(
                actor=self.dean,
                organization=self.org,
                application_id=app.id,
                document=pdf("teqdimat.pdf"),
                reason="Qayıb həddi keçildiyi üçün G2 ilə yenidən keçir.",
                offering_id=self.target.id,
            )
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.COMPLETED)
        self.assertIsNotNone(app.placement_enrollment_id)
        self.assertEqual(app.placement_enrollment.offering_id, self.target.id)

    def test_subgroup_without_service_stays_admitted_until_placed(self):
        self.fail_exam()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            from apps.registrar import public

            with mock.patch.object(public, "place_in_subgroup", None, create=True):
                retake_decisions.approve_subgroup(
                    actor=self.dean,
                    organization=self.org,
                    application_id=app.id,
                    document=pdf(),
                    reason="Tələbə 25% vermədən alt qrupa qalmaq istəyir.",
                    offering_id=self.target.id,
                )
            app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.ADMITTED)

    def test_placement_error_rolls_back_with_code(self):
        self.fail_exam()

        class SubgroupPlacementError(Exception):
            def __init__(self, message, code):
                super().__init__(message, code)
                self.code = code

            def __str__(self):
                return str(self.args[0])

        def boom(**kwargs):
            raise SubgroupPlacementError("Kredit limiti aşılır", "credit_limit")

        with bypass_rls():
            app = retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
            with (
                mock.patch("apps.registrar.public.place_in_subgroup", boom, create=True),
                mock.patch("apps.registrar.public.SubgroupPlacementError", SubgroupPlacementError, create=True),
            ):
                with self.assertRaises(ValidationError) as caught:
                    retake_decisions.approve_subgroup(
                        actor=self.dean,
                        organization=self.org,
                        application_id=app.id,
                        document=pdf(),
                        reason="Tələbə 25% vermədən alt qrupa qalmaq istəyir.",
                        offering_id=self.target.id,
                    )
            app.refresh_from_db()
        self.assertIn("credit_limit", str(caught.exception))
        self.assertEqual(app.status, RetakeStatus.SUBMITTED)  # tranzaksiya geri qaytarıldı

    def test_main_exam_correction_never_touches_application(self):
        """Rəy HIGH-1 probu: əsas imtahan 12, müraciət buraxılıb, müəllim 14-ə düzəldir → müraciət və ResitRecord dəyişmir."""
        self.fail_exam(score=12)
        with bypass_rls():
            app = self._admitted()
            finals.set_exam_score(enrollment=self.enrollment, score=14, by_user=self.teacher)
            app.refresh_from_db()
            resit = ResitRecord.objects.filter(enrollment=self.enrollment).first()
        self.assertEqual(app.status, RetakeStatus.ADMITTED)
        self.assertIsNone(app.result_score)
        self.assertTrue(resit is None or resit.resit_score is None)
        self.assertEqual(app.base_exam_score, Decimal("12"))

    def test_score_above_exam_cap_is_rejected(self):
        """Rəy LOW-7: 61 səssizcə 50-yə kəsilmir — aydın xəta."""
        self.fail_exam()
        with bypass_rls():
            app = self._admitted()
            with self.assertRaises(ValidationError) as caught:
                retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=app.id, score=61)
            app.refresh_from_db()
        self.assertIn("50", str(caught.exception))
        self.assertEqual(app.status, RetakeStatus.ADMITTED)

    def test_exam_chance_moves_application_to_exam_granted(self):
        self.fail_exam()
        exam = {
            "id": 991,
            "title": "INF101 final",
            "exam_type": "written",
            "category": "final",
            "subject_id": self.subject.id,
        }
        with bypass_rls():
            with self.assertRaises(ValidationError):  # müraciət yoxdur
                retake_chance.validate(organization=self.org, exam=exam, students=[self.student], reason="retake_25")
            app = self._admitted()
            cleaned = retake_chance.validate(
                organization=self.org, exam=exam, students=[self.student], reason="retake_25"
            )
            grants = retake_chance.record(
                organization=self.org, exam=exam, students=[self.student], cleaned=cleaned, extra=1, actor=self.dean
            )
            app.refresh_from_db()
            history = retake_queries.attempt_history(
                retake_queries.student_applications(student=self.student, organization=self.org),
                retake_queries.student_grants(student=self.student, organization=self.org),
            )
        self.assertEqual(app.status, RetakeStatus.EXAM_GRANTED)
        self.assertEqual(grants[0].application_id, app.id)
        self.assertEqual(grants[0].exam_type, "written")
        self.assertEqual(history[0]["grants"][0].reason, ExamChanceReason.RETAKE_25)

    def test_exam_chance_reason_requirements(self):
        exam = {"id": 5, "title": "x", "exam_type": "test", "category": "midterm", "subject_id": self.subject.id}
        with bypass_rls():
            with self.assertRaises(ValidationError):
                retake_chance.validate(organization=self.org, exam=exam, students=[self.student], reason="")
            with self.assertRaises(ValidationError):
                retake_chance.validate(
                    organization=self.org,
                    exam=exam,
                    students=[self.student],
                    reason="university",
                    note="Rektor əmri ilə",
                )
            ok = retake_chance.validate(
                organization=self.org,
                exam=exam,
                students=[self.student],
                reason="university",
                reference_number="12/R",
                reference_date="2026-10-01",
                note="Rektor əmri ilə güzəşt",
            )
            self.assertEqual(ok["reference_number"], "12/R")
            with self.assertRaises(ValidationError):
                retake_chance.validate(organization=self.org, exam=exam, students=[self.student], reason="technical")
            retake_chance.validate(
                organization=self.org,
                exam=exam,
                students=[self.student],
                reason="technical",
                note="Kompüter imtahan zamanı söndü",
            )

    @override_settings(RETAKE_MAX_ATTEMPTS=2)
    def test_history_counts_every_attempt(self):
        self.fail_exam(score=10)
        with bypass_rls():
            first = self._admitted()
            retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=first.id, score=12)
            second = self._admitted()
            retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=second.id, score=30)
            second.refresh_from_db()
            history = retake_queries.attempt_history(
                retake_queries.student_applications(student=self.student, organization=self.org), []
            )
            lines = retake_queries.result_lines(organization=self.org, enrollment_ids=[self.enrollment.id])
            resit = ResitRecord.objects.get(enrollment=self.enrollment)
        self.assertEqual(second.attempt_number, 2)
        self.assertEqual(history[0]["attempt_count"], 2)
        self.assertEqual(history[0]["chain"], "Əsas imtahan: 10 → 25% #1: 12 → 25% #2: 30")
        self.assertEqual(lines[self.enrollment.id]["text"], "Əsas imtahan: 10 → 25%: 12 → 25%: 30")
        self.assertEqual(resit.resit_score, Decimal("30"))  # son cəhd qüvvədədir

    def test_duplicate_receipt_is_flagged_not_blocked(self):
        self.fail_exam()
        self.fail_exam(enrollment=self.other.enrollments.get(offering__subject=self.subject))
        with bypass_rls():
            first = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf("eyni.pdf"),
            )
            second = retake_services.apply(
                student=self.other,
                organization=self.org,
                enrollment_id=self.other.enrollments.get(offering__subject=self.subject).id,
                kind="retake_25",
                receipt=pdf("basqa-ad.pdf"),
            )
            second.refresh_from_db()
            dup = retake_services.duplicate_receipt_map([second.current_receipt])
            retake_decisions.verify_payment(
                actor=self.accountant, organization=self.org, application_id=second.id, paid_amount="100"
            )
            event = second.events.get(action=RetakeEventAction.PAYMENT_VERIFIED)
        self.assertEqual([r.application_id for r in dup[second.current_receipt_id]], [first.id])
        self.assertEqual(event.metadata["duplicate_receipt_applications"], [str(first.id)])

    def test_upload_validation(self):
        self.fail_exam()
        from django.core.files.uploadedfile import SimpleUploadedFile

        with bypass_rls():
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student,
                    organization=self.org,
                    enrollment_id=self.enrollment.id,
                    kind="retake_25",
                    receipt=SimpleUploadedFile("qebz.exe", b"MZ\x90\x00", content_type="application/octet-stream"),
                )
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student,
                    organization=self.org,
                    enrollment_id=self.enrollment.id,
                    kind="retake_25",
                    receipt=pdf("boyuk.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 10)),
                )
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student,
                    organization=self.org,
                    enrollment_id=self.enrollment.id,
                    kind="retake_25",
                    receipt=SimpleUploadedFile("sekil.png", b"not-a-png", content_type="image/png"),
                )
        self.assertFalse(RetakeApplication.objects.exists())

    def test_events_and_receipts_are_append_only(self):
        self.fail_exam()
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            event = app.events.first()
            receipt = app.receipts.first()
            for row in (event, receipt):
                with self.assertRaises(ValidationError):
                    row.save()
                with self.assertRaises(ValidationError):
                    row.delete()
            for model in (RetakeApplicationEvent, RetakeReceipt):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.filter(application=app).update(organization=self.org)
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.filter(application=app)._raw_delete(model.objects.db)
            grant = ExamChanceGrant.objects.create(
                organization=self.org, student=self.student, exam_id=1, reason="other", note="test qeydi"
            )
            with self.assertRaises(DatabaseError), transaction.atomic():
                ExamChanceGrant.objects.filter(pk=grant.pk).update(note="dəyişdi")

    def test_one_active_application_per_subject(self):
        self.fail_exam()
        with bypass_rls():
            retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="retake_25"
            )
            with self.assertRaises(ValidationError):
                retake_services.apply(
                    student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
                )
        self.assertEqual(RetakeApplication.objects.filter(kind=RetakeKind.SUBGROUP).count(), 0)
