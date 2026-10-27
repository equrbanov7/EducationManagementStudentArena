"""Superadmin sənədsiz düzəliş (sahib 2026-10-27) — registrar qapıları.

Sahib: «əmr və s. nə isə yükləmədən rahatlıqla nə isə silib dəyişə bilim». Hər qapı üçün iki hal:

* superadmin sənədsiz keçir — tarixçə / audit sətrində «Superadmin düzəlişi — sənədsiz (ad, tarix)» qeydi var;
* adi rol üçün qayda DƏYİŞMƏYİB — sənəd yenə məcburidir.

Qapılar: alt qrupa yerləşdirmə (alət + jurnal modalı), jurnalın rəsmi düzəlişi (xana / dərs silmə), imtahan
balının təqdimatlı dəyişikliyi, 25% bağlanış qərarı, yenidən imtahan cəhdi, xarici nəticənin tanınması.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import corrections
from apps.registrar import exam_score_entry as exam_service
from apps.registrar import finals
from apps.registrar import legacy_grade_review_actions as review_write
from apps.registrar import retake_chance, retake_closure, retake_decisions
from apps.registrar.models import (
    CorrectionField,
    CorrectionReason,
    Enrollment,
    ExamChanceReason,
    ExamScoreEntry,
    ExamScoreEntryKind,
    ExternalCreditRecognition,
    FinalGrade,
    JournalCorrection,
    LessonCorrection,
    SubgroupPlacementEvent,
)
from apps.registrar.public import SubgroupPlacementError
from apps.registrar.tests import test_exam_score_entry as exam_fixture
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from apps.registrar.tests.test_credit_recognition import _RecognitionBase
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from apps.registrar.tests.test_legacy_grade_review import _ReviewSetup
from apps.registrar.tests.test_subgroup_placement import _Base as _SubgroupBase
from core import superadmin_waiver
from core.rls import bypass_rls

User = get_user_model()

_MEDIA = tempfile.mkdtemp(prefix="sa-waiver-media-")


def _superuser(username):
    return User.objects.create_user(username, f"{username}@qku.edu.az", "pw", is_superuser=True)


class WaiverHelperTest(TestCase):
    def test_only_authenticated_superadmin_waives(self):
        admin = _superuser("saw_helper_admin")
        plain = User.objects.create_user("saw_helper_plain", "saw_helper_plain@qku.edu.az", "pw")
        self.assertTrue(superadmin_waiver.waives(admin))
        self.assertFalse(superadmin_waiver.waives(plain))
        self.assertFalse(superadmin_waiver.waives(None))
        self.assertEqual(superadmin_waiver.stamp("səbəb", plain), "səbəb")
        stamped = superadmin_waiver.stamp("səbəb", admin)
        self.assertTrue(stamped.startswith("səbəb · " + superadmin_waiver.NOTE_PREFIX))
        self.assertEqual(superadmin_waiver.stamp(stamped, admin), stamped)  # təkrar əlavə olunmur
        self.assertTrue(superadmin_waiver.order_number().startswith(superadmin_waiver.ORDER_PREFIX))

    def test_waiver_pdf_is_a_real_pdf_with_the_note(self):
        import fitz

        admin = _superuser("saw_helper_pdf")
        payload = superadmin_waiver.waiver_pdf(admin, subject="Fizika").read()
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertLess(len(payload), 200_000)
        text = fitz.open(stream=payload, filetype="pdf").load_page(0).get_text()
        self.assertIn(superadmin_waiver.NOTE_PREFIX, text)


# ── Alt qrupa yerləşdirmə (alət servisi) ─────────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=_MEDIA)
class SubgroupPlacementWaiverTest(_SubgroupBase):
    PREFIX = "sgw"

    def test_superadmin_places_without_document_or_reason(self):
        admin = _superuser("sgw_admin")
        result = self.place(actor=admin, document=None, reason="")
        with bypass_rls():
            event = SubgroupPlacementEvent.objects.get(pk=result["event"].pk)
        self.assertIsNone(event.document_id)
        self.assertTrue(event.order_number.startswith(superadmin_waiver.ORDER_PREFIX))
        self.assertIsNotNone(event.order_date)
        self.assertIn(superadmin_waiver.NOTE_PREFIX, event.reason)

    def test_regular_dean_still_needs_a_document(self):
        with self.assertRaises(SubgroupPlacementError) as caught:
            self.place(document=None)
        self.assertEqual(caught.exception.code, "document_required")


# ── Alt qrupa yerləşdirmə (jurnal modalı) ────────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=_MEDIA)
class JournalGuestAddWaiverTest(_GuestRosterBase):
    def _add(self, user):
        self._drop_own_history(self.guest)
        return self._client(user).post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )

    def test_superadmin_adds_without_document(self):
        response = self._add(_superuser("gr_sa_admin"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        with bypass_rls():
            enrollment = Enrollment.objects.get(pk=response.json()["enrollment_id"])
            self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)
            event = SubgroupPlacementEvent.objects.filter(enrollment=enrollment).first()
        if event is not None:  # kredit planı varsa tarixçə sətri də yazılır
            self.assertIsNone(event.document_id)
            self.assertIn(superadmin_waiver.NOTE_PREFIX, event.reason)

    def test_coordinator_still_needs_a_document(self):
        response = self._add(self.coordinator)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        with bypass_rls():
            self.assertFalse(
                Enrollment.objects.filter(
                    offering=self.offering, student=self.guest, status=Enrollment.Status.ENROLLED
                ).exists()
            )


# ── Jurnalın rəsmi düzəlişi (səbəb + qeyd + PDF) ─────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=_MEDIA)
class JournalCorrectionWaiverTest(_BaseJournalSetup):
    def test_superadmin_corrects_cell_without_reason_note_or_pdf(self):
        _lesson, mark = self._seminar_mark(13, 3)
        with bypass_rls():
            correction = corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=7,
                reason="",
                note="",
                document=None,
                by_user=self.admin,
            )
            correction = JournalCorrection.objects.get(pk=correction.pk)
            mark.refresh_from_db()
        self.assertEqual(mark.score, 7)
        self.assertEqual(correction.reason, CorrectionReason.OTHER)
        self.assertTrue(correction.note.startswith(superadmin_waiver.NOTE_PREFIX))
        self.assertTrue(correction.document.name.endswith(".pdf"))  # sənədin olmadığını bildirən PDF

    def test_superadmin_deletes_locked_lesson_without_document(self):
        lesson, _mark = self._seminar_mark(14, 3)
        with bypass_rls():
            correction = corrections.apply_lesson_deletion(
                lesson=lesson, reason="", note="", document=None, by_user=self.admin
            )
            self.assertTrue(LessonCorrection.objects.filter(pk=correction.pk, is_deletion=True).exists())
            self.assertFalse(type(lesson).objects.filter(pk=lesson.pk).exists())
        self.assertIn(superadmin_waiver.NOTE_PREFIX, correction.note)

    def test_regular_corrector_still_needs_the_pdf(self):
        _lesson, mark = self._seminar_mark(15, 3)
        with bypass_rls(), self.assertRaises(ValidationError):
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=7,
                reason=CorrectionReason.TECHNICAL,
                note="Səhv yazılıb",
                document=None,
                by_user=self.teacher,
            )
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal(3))


# ── İmtahan balının təqdimatlı dəyişikliyi ───────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=exam_fixture._MEDIA)
class ExamScoreChangeWaiverTest(TestCase):
    setUp = exam_fixture.ExamScoreEntryServiceTest.setUp

    def test_superadmin_changes_written_score_without_document(self):
        admin = _superuser("ese_sa_admin")
        with bypass_rls():
            exam_service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            entry = exam_service.record_exam_score(enrollment=self.enrollment_a1, score="30", by_user=admin)
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("30"))
        self.assertEqual(entry.kind, ExamScoreEntryKind.CORRECTION)
        self.assertEqual(entry.reason, CorrectionReason.OTHER)
        self.assertTrue(entry.note.startswith(superadmin_waiver.NOTE_PREFIX))
        self.assertFalse(entry.evidence)

    def test_regular_actor_still_needs_a_document(self):
        with bypass_rls():
            exam_service.record_exam_score(enrollment=self.enrollment_a1, score="45", by_user=self.center)
            with self.assertRaises(ValidationError):
                exam_service.record_exam_score(
                    enrollment=self.enrollment_a1,
                    score="30",
                    by_user=self.center,
                    reason=CorrectionReason.TECHNICAL,
                    note="Vərəq yenidən yoxlanıldı",
                )
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment_a1).exam_score, Decimal("45"))


# ── Köhnə rəsmi balın düzəlişi (yoxlama növbəsi) ─────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=_MEDIA)
class LegacyReviewWaiverTest(_ReviewSetup):
    def test_superadmin_corrects_without_note_or_document(self):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=Decimal("10"), by_user=self.admin)
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))
        with bypass_rls():
            review_write.apply_correction(
                organization=self.org,
                fact_id=str(fact.pk),
                score="17",
                reason="",
                note="",
                evidence=None,
                actor=self.admin,
            )
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("17"))
            entry = ExamScoreEntry.objects.filter(enrollment=self.enrollment).latest("created_at")
        self.assertIn(superadmin_waiver.NOTE_PREFIX, entry.note)
        self.assertFalse(entry.evidence)


# ── 25% bağlanış qərarı (əmr № + tarix VƏ YA sənəd) ─────────────────────────────────────────────


class RetakeDecisionWaiverTest(TestCase):
    def test_superadmin_closure_gets_an_automatic_order(self):
        admin = _superuser("rtw_admin")
        decision = retake_closure.clean_decision(actor=admin)
        self.assertTrue(decision["number"].startswith(superadmin_waiver.ORDER_PREFIX))
        self.assertIsNotNone(decision["date"])
        self.assertIsNone(decision["document"])
        self.assertIn(superadmin_waiver.NOTE_PREFIX, retake_decisions._waiver_reason("", admin, None))

    def test_regular_actor_still_needs_order_or_document(self):
        plain = User.objects.create_user("rtw_plain", "rtw_plain@qku.edu.az", "pw")
        with self.assertRaises(ValidationError):
            retake_closure.clean_decision(actor=plain)
        with self.assertRaises(ValidationError):
            retake_closure.clean_decision()
        self.assertEqual(retake_decisions._waiver_reason("qısa", plain, None), "qısa")


# ── Yenidən imtahan cəhdi (əsas sənəd) ───────────────────────────────────────────────────────────


class ExamChanceWaiverTest(TestCase):
    exam = {"id": 1, "category": "midterm", "subject_id": None}

    def _validate(self, actor, **extra):
        student = User.objects.create_user(f"ecw_st_{actor.username}", f"ecw_{actor.username}@qku.edu.az", "pw")
        return retake_chance.validate(
            organization=None,
            exam=self.exam,
            students=[student],
            reason=extra.pop("reason", ExamChanceReason.UNIVERSITY),
            actor=actor,
            **extra,
        )

    def test_superadmin_grants_without_document_order_or_note(self):
        cleaned = self._validate(_superuser("ecw_admin"))
        self.assertIsNone(cleaned["document"])
        self.assertTrue(cleaned["reference_number"].startswith(superadmin_waiver.ORDER_PREFIX))
        self.assertIsNotNone(cleaned["reference_date"])
        self.assertTrue(cleaned["note"].startswith(superadmin_waiver.NOTE_PREFIX))

    def test_regular_actor_still_needs_the_document(self):
        plain = User.objects.create_user("ecw_plain", "ecw_plain@qku.edu.az", "pw")
        with self.assertRaises(ValidationError):
            self._validate(plain, reason=ExamChanceReason.TECHNICAL, note="Kompüter imtahan zamanı söndü")


# ── Xarici nəticənin tanınması (əsas sənəd) ──────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=_MEDIA)
class CreditRecognitionWaiverTest(_RecognitionBase):
    def test_superadmin_recognises_without_document(self):
        admin = _superuser("cr_sa_admin")
        response = self._create(user=admin, document=None)
        self.assertEqual(response.status_code, 200, response.content)
        recognition = self._recognition()
        self.assertTrue(recognition.document.name.endswith(".pdf"))
        self.assertIn(superadmin_waiver.NOTE_PREFIX, recognition.note)
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_id=str(recognition.pk), reason__contains=superadmin_waiver.NOTE_PREFIX
                ).exists()
            )

    def test_dean_still_needs_the_document(self):
        response = self._create(document=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "document_required")
        with bypass_rls():
            self.assertFalse(ExternalCreditRecognition.objects.exists())
