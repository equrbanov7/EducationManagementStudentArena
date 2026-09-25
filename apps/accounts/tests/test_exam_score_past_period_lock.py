"""Bitmiş dövr kilidi + RİM rəhbərinin düzəliş rejimi — «İmtahan balının daxil edilməsi» (2026-09-26).

Sahib: «burda köhnə ilin balını dəyişmək olmamalıdır, ancaq RİM rəhbəri
tərəfindən təqdimat əsasında ola bilər … «düzəliş aktivləşdir» düyməsi …
file yükləmə yeri də olsun, məcburi həm də.»

Yoxlanan müqavilə (server tərəfdə — UI yalnız əks etdirir):

* bitmiş dövrdə İmtahan Mərkəzi nə ilk bal, nə dəyişiklik, nə də idxal yaza bilər;
* RİM rəhbəri düzəliş rejimi aktivləşdirilmədən yaza bilməz;
* rejim aktivdirsə səbəb / qeyd / skan (hər biri) olmadan rədd; üçü ilə yazılır + audit;
* cari dövr dəyişmir (ilk bal sərbəst, dəyişiklik təqdimatlı) — dialoqun yeni fayl sahəsi
  (``justification_evidence``) partiyanın skanı kimi qəbul olunur;
* dialoq fayl sahəsini render edir; yalnız RİM rəhbəri / superadmin düyməni görür.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.organizations.models import AcademicPeriod, Membership
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_period_lock as lock
from apps.registrar.models import CorrectionReason, ExamScoreEntry, ExamScoreEntryKind, ExamScoreSheet, FinalGrade
from core.rls import bypass_rls

User = get_user_model()

PROFILE_PARAMS = {"section": "exam-score-entry"}


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=fixtures._MEDIA)
class PastPeriodLockTest(TestCase):
    """Bölmə fixture-u kompozisiya ilə (`test_w6_exam_score_import_view.py` naxışı)."""

    _client = fixtures.ExamScoreEntrySectionTest._client

    @classmethod
    def setUpTestData(cls):
        fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__(cls)
        with bypass_rls():
            cls.rim = cls._member("eses_rim_head", "ikt_rehber")
            cls.rector = cls._member("eses_rector", "rector")

    @classmethod
    def _member(cls, username, role):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
        )
        return user

    def setUp(self):
        with bypass_rls():
            # Fixture dövrü 2024/2025 Payız (bitib) — «cari» işarəsi götürülür → KİLİDLİ.
            AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=False)

    # ── köməkçilər ───────────────────────────────────────────────────────────
    def _unlock_period(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=True)

    def _seed_score(self, value="45"):
        """Kilidə baxmayan birbaşa servis yazısı (köhnə il üçün mövcud bal)."""
        with bypass_rls():
            service.record_exam_score(enrollment=self.enrollment, score=value, by_user=self.center)

    def _post(self, user, **extra):
        payload = {
            "action": "save_scores",
            "offering_id": str(self.offering.id),
            f"score__{self.enrollment.id}": "45",
        }
        payload.update(extra)
        return self._client(user).post(reverse("accounts:exam_score_entry"), payload)

    def _full_submission(self, **extra):
        return {
            "correction_mode": "1",
            "reason": CorrectionReason.APPEAL,
            "note": "RİM təqdimatı № 12",
            "justification_evidence": fixtures._pdf("teqdimat.pdf"),
            **extra,
        }

    def _page(self, user, **params):
        return self._client(user).get(
            reverse("accounts:profile"), {**PROFILE_PARAMS, "ese_offering": str(self.offering.id), **params}
        )

    def _import(self, user, **extra):
        csv = SimpleUploadedFile("ballar.csv", f"username,Bal\n{self.student.username},40\n".encode())
        payload = {"file": csv, "offering_id": str(self.offering.id), "question_count": "0", **extra}
        return self._client(user).post(reverse("accounts:exam_score_import_apply"), payload)

    def _score(self):
        with bypass_rls():
            grade = FinalGrade.objects.filter(enrollment=self.enrollment).first()
            return grade.exam_score if grade is not None else None

    def _entries(self):
        with bypass_rls():
            return list(ExamScoreEntry.objects.filter(enrollment=self.enrollment).order_by("created_at"))

    def _sheet_count(self):
        with bypass_rls():
            return ExamScoreSheet.objects.filter(offering=self.offering).count()

    # ── qayda ────────────────────────────────────────────────────────────────
    def test_lock_rule(self):
        with bypass_rls():
            period = AcademicPeriod.objects.get(pk=self.period.pk)
        today = timezone.localdate()
        self.assertTrue(lock.period_is_locked(period, today))
        period.is_current = True
        self.assertFalse(lock.period_is_locked(period, today))  # «cari» işarəsi üstündür
        period.is_current = False
        period.exam_session_end = today  # imtahan sessiyası hələ açıqdır
        self.assertFalse(lock.period_is_locked(period, today))
        period.exam_session_end = today - datetime.timedelta(days=1)
        self.assertTrue(lock.period_is_locked(period, today))

    def test_only_rim_head_and_superadmin_can_unlock(self):
        with bypass_rls():
            superadmin = User.objects.create_superuser("eses_su", "eses_su@qku.edu.az", "pw")
            self.assertTrue(lock.can_unlock_past_period(self.rim, self.org))
            self.assertTrue(lock.can_unlock_past_period(superadmin, self.org))
            self.assertFalse(lock.can_unlock_past_period(self.center, self.org))
            # `*` daşıyan rektor da AÇA BİLMİR — sahib: «ancaq RİM rəhbəri».
            self.assertFalse(lock.can_unlock_past_period(self.rector, self.org))

    # ── İmtahan Mərkəzi: bitmiş dövrdə heç bir yazı ─────────────────────────
    def test_center_page_is_read_only(self):
        resp = self._page(self.center)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-ese-period-lock")
        self.assertContains(resp, 'data-read-only="1"')
        self.assertNotContains(resp, "data-ese-save")
        self.assertNotContains(resp, "data-esi-apply")
        self.assertNotContains(resp, "data-ese-correction-on")

    def test_center_cannot_write_first_entry(self):
        resp = self._post(self.center)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._score())
        self.assertEqual(self._sheet_count(), 0)

    def test_center_cannot_write_even_with_forged_correction_mode(self):
        self._post(self.center, **self._full_submission())
        self.assertIsNone(self._score())
        self.assertEqual(self._sheet_count(), 0)

    def test_center_cannot_change_existing_score(self):
        self._seed_score("45")
        self._post(self.center, **self._full_submission(**{f"score__{self.enrollment.id}": "30"}))
        self.assertEqual(self._score(), Decimal("45"))
        self.assertEqual(len(self._entries()), 1)

    def test_center_import_apply_is_forbidden(self):
        resp = self._import(self.center, **self._full_submission())
        self.assertEqual(resp.status_code, 403)
        self.assertIsNone(self._score())
        self.assertEqual(self._sheet_count(), 0)

    def test_service_rejects_center_even_in_correction_mode(self):
        with bypass_rls(), self.assertRaises(PermissionDenied):
            service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(self.enrollment.id), "score": "40"}],
                by_user=self.center,
                correction_mode=True,
            )

    # ── RİM rəhbəri: rejim + təqdimat ───────────────────────────────────────
    def test_rim_head_sees_activate_button(self):
        resp = self._page(self.rim)
        self.assertContains(resp, "data-ese-correction-on")
        self.assertContains(resp, "ese_correct=1")
        self.assertNotContains(resp, "data-ese-save")

    def test_rim_head_correction_mode_renders_form_and_file_input(self):
        resp = self._page(self.rim, ese_correct="1")
        self.assertContains(resp, 'data-correction-mode="1"')
        self.assertContains(resp, 'name="correction_mode" value="1"')
        self.assertContains(resp, "data-ese-correction-off")
        self.assertContains(resp, "data-ese-save")
        self.assertContains(resp, 'name="justification_evidence"')
        self.assertContains(resp, "data-ese-just-file")
        self.assertContains(resp, "data-esi-evidence")
        # Yadda saxlamadan sonra səhifə düzəliş rejimində qalır (`next` rejimi daşıyır).
        self.assertRegex(resp.content.decode(), r'name="next" value="[^"]*ese_correct=1')

    def test_forged_ese_correct_does_not_unlock_for_center(self):
        resp = self._page(self.center, ese_correct="1")
        self.assertContains(resp, 'data-read-only="1"')
        self.assertNotContains(resp, 'name="correction_mode"')

    def test_rim_head_without_correction_mode_is_rejected(self):
        submission = self._full_submission()
        submission.pop("correction_mode")
        self._post(self.rim, **submission)
        self.assertIsNone(self._score())
        self.assertEqual(self._sheet_count(), 0)
        with bypass_rls(), self.assertRaises(PermissionDenied):
            service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(self.enrollment.id), "score": "40"}],
                by_user=self.rim,
            )

    def test_rim_head_import_without_correction_mode_is_forbidden(self):
        submission = self._full_submission()
        submission.pop("correction_mode")
        resp = self._import(self.rim, **submission)
        self.assertEqual(resp.status_code, 403)
        self.assertIsNone(self._score())

    def test_rim_head_correction_mode_requires_each_part_of_submission(self):
        for missing in ("reason", "note", "justification_evidence"):
            with self.subTest(missing=missing):
                submission = self._full_submission()
                submission.pop(missing)
                self._post(self.rim, **submission)
                self.assertIsNone(self._score())
                self.assertEqual(self._sheet_count(), 0)

    def test_rim_head_import_requires_submission(self):
        submission = self._full_submission()
        submission.pop("justification_evidence")
        resp = self._import(self.rim, **submission)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "submission_required")
        self.assertIsNone(self._score())

    def test_rim_head_first_entry_with_submission_is_written_and_audited(self):
        from apps.audit.models import AuditLog

        resp = self._post(self.rim, **self._full_submission())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._score(), Decimal("45"))
        (entry,) = self._entries()
        self.assertEqual(entry.kind, ExamScoreEntryKind.CORRECTION)  # «Dəyişən nəticələr»də izlənir
        self.assertEqual(entry.reason, CorrectionReason.APPEAL)
        self.assertEqual(entry.note, "RİM təqdimatı № 12")
        with bypass_rls():
            self.assertTrue(entry.sheet.evidence)
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.exam_score_entry",
                    resource_id=str(entry.pk),
                    reason__contains="past-period correction",
                ).exists()
            )

    def test_rim_head_change_with_meta_card_scan_is_written(self):
        self._seed_score("45")
        submission = self._full_submission(**{f"score__{self.enrollment.id}": "30"})
        submission.pop("justification_evidence")
        submission["sheet_evidence"] = fixtures._pdf("protokol.pdf")  # vərəq kartındakı sahə də qəbul olunur
        self._post(self.rim, **submission)
        self.assertEqual(self._score(), Decimal("30"))
        self.assertEqual(len(self._entries()), 2)

    def test_rim_head_import_with_submission_is_written(self):
        resp = self._import(self.rim, **self._full_submission())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["result"]["written"], 1)
        self.assertEqual(self._score(), Decimal("40"))
        (entry,) = self._entries()
        self.assertEqual(entry.reason, CorrectionReason.APPEAL)

    # ── cari dövr: davranış dəyişmir ────────────────────────────────────────
    def test_current_period_first_entry_is_free(self):
        self._unlock_period()
        resp = self._page(self.center)
        self.assertNotContains(resp, "data-ese-period-lock")
        self.assertContains(resp, 'data-read-only="0"')
        self.assertContains(resp, 'name="justification_evidence"')  # dialoqun fayl sahəsi
        self._post(self.center)
        self.assertEqual(self._score(), Decimal("45"))
        (entry,) = self._entries()
        self.assertEqual(entry.kind, ExamScoreEntryKind.INITIAL)

    def test_current_period_change_requires_scan_and_accepts_dialog_file(self):
        self._unlock_period()
        self._post(self.center)
        change = {
            f"score__{self.enrollment.id}": "30",
            "reason": CorrectionReason.APPEAL,
            "note": "Apellyasiya",
        }
        self._post(self.center, **change)  # skan yoxdur → rədd
        self.assertEqual(self._score(), Decimal("45"))
        self._post(self.center, **change, justification_evidence=fixtures._pdf())
        self.assertEqual(self._score(), Decimal("30"))
        self.assertEqual(len(self._entries()), 2)
