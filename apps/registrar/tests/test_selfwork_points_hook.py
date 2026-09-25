"""«Fənn qovluğu» → jurnal hook-u: ``public_services.selfwork_points.record_points`` / ``preview``.

Müqavilə (``apps/subject_folder/public.py`` §9 + W3 brifi):

* dəqiq imza (yalnız açar sözlər) və ``(ok, mesaj)`` qaytarışı;
* kilidli jurnal / aktiv olmayan qeydiyyat / şkala uyğunsuzluğu / etibarsız bal → ``False`` + izah;
* İKİNCİ BAL YOXDUR: slotda hər hansı mənbədən bal varsa imtina; eyni ``source_ref`` +
  eyni bal — idempotent ``True``; sənədli düzəlişlə silinmiş bal yenidən yazılmır;
* cəm ≤ 10; struktur yoxdursa/uyğunsuzdursa imtina; ilk bal strukturu sillabusdan qurur;
* yazı: ``done, points, source, source_ref, graded_at, entered_by`` + qiymət auditi;
* ``preview`` — YAZISIZ, ≤ 3 sorğu;
* paralel iki çağırış (PostgreSQL sətir kilidi) → TƏK bal.
"""

from __future__ import annotations

import inspect
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

import pytest

from apps.registrar import gradebook, item_corrections, journal_extras
from apps.registrar.models import (
    ApprovalStatus,
    AssessmentScheme,
    CorrectionReason,
    Enrollment,
    SelfWorkMark,
    SelfWorkTopic,
)
from apps.registrar.public_services import selfwork_points as hook
from apps.registrar.tests.selfwork_points_fixture import SelfWorkLegacyFixture, approve_syllabus
from core.rls import bypass_rls


def _ref():
    return f"subject_folder.submission:{uuid.uuid4()}"


def _lock(organization, offering):
    """RİM-in bağladığı jurnal (``registrar_scheme_publish_state_valid``: yayımlanmış = təsdiqlənmiş)."""
    AssessmentScheme.objects.update_or_create(
        organization=organization,
        offering=offering,
        defaults={"is_published": True, "approval_status": ApprovalStatus.APPROVED},
    )


def _pdf():
    """%PDF magic — ``core.upload_security`` imza yoxlamasından keçsin."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("esas.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class HookContractTest(SelfWorkLegacyFixture, TestCase):
    def setUp(self):
        self.offering, self.enrollments = self._fresh_offering(code="SWH1", option="2x5")
        self.enrollment = self.enrollments["swp_s0"]

    def _record(self, *, slot=2, max_points="5.0", points="4.0", ref=None, enrollment=None, offering=None):
        with bypass_rls():
            return hook.record_points(
                offering=offering or self.offering,
                enrollment=enrollment or self.enrollment,
                slot_index=slot,
                slot_title="Python-da siyahılar",
                max_points=Decimal(max_points),
                points=Decimal(points),
                source_ref=ref or _ref(),
                by_user=self.teacher,
            )

    # ── imza ────────────────────────────────────────────────────────────────
    def test_exact_keyword_only_signature_is_exported(self):
        params = inspect.signature(hook.record_points).parameters
        self.assertEqual(
            list(params),
            ["offering", "enrollment", "slot_index", "slot_title", "max_points", "points", "source_ref", "by_user"],
        )
        self.assertTrue(all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values()))
        self.assertEqual(
            list(inspect.signature(hook.preview).parameters), ["offering", "enrollment", "slot_index", "points"]
        )
        from apps.registrar import public

        self.assertIs(public.selfwork_points, hook, "apps.registrar.public da re-eksport edir")

    def test_subject_folder_resolves_this_hook(self):
        try:
            from apps.subject_folder.services import journal as folder_journal
        except Exception:  # pragma: no cover — qonşu app yarımçıqdırsa
            self.skipTest("apps.subject_folder yüklənmədi")
        self.assertIs(folder_journal.resolve_journal_hook(), hook.record_points)

    # ── uğurlu yazı ─────────────────────────────────────────────────────────
    def test_first_award_builds_structure_and_writes_audited_points(self):
        ref = _ref()
        ok, message = self._record(ref=ref)
        self.assertTrue(ok, message)
        self.assertEqual(message, "Jurnala yazıldı: Sərbəst iş 2 · 4/5 (cəmi 4/10)")
        with bypass_rls():
            topics = list(SelfWorkTopic.objects.filter(offering=self.offering).order_by("slot_index"))
            mark = SelfWorkMark.objects.get(topic__slot_index=2, enrollment=self.enrollment)
            entry = gradebook.entry_score_for(self.enrollment, 50)
            history = gradebook.grade_audit.get_grade_history(offering=self.offering)
        self.assertEqual([(t.slot_index, t.max_points) for t in topics], [(1, 5), (2, 5)])
        self.assertEqual(
            (mark.done, mark.points, mark.source, mark.source_ref, mark.entered_by_id),
            (True, Decimal("4.0"), "subject_folder", ref, self.teacher.id),
        )
        self.assertIsNotNone(mark.graded_at)
        self.assertEqual(entry, Decimal("4"), "bal giriş balına düşür")
        rows = [change for entry_row in history for change in entry_row["changes"]]
        self.assertTrue(any("Fənn qovluğu" in str(c.get("item")) and c.get("new") == "4" for c in rows), rows)

    def test_fractional_folder_points_are_kept(self):
        ok, message = self._record(slot=1, points="4.5")
        self.assertTrue(ok, message)
        self.assertIn("4.5/5", message)

    # ── imtinalar ──────────────────────────────────────────────────────────
    def test_locked_journal_is_refused(self):
        with bypass_rls():
            _lock(self.org, self.offering)
        ok, message = self._record()
        self.assertFalse(ok)
        self.assertTrue(message.startswith("Jurnal kilidlidir"), message)
        self.assertFalse(SelfWorkMark.objects.filter(enrollment=self.enrollment).exists())

    def test_inactive_or_foreign_enrollment_is_refused(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status=Enrollment.Status.DROPPED)
        ok, message = self._record()
        self.assertFalse(ok)
        self.assertIn("aktiv qeydiyyatda deyil", message)
        ok, _message = self._record(enrollment=self.e1["swp_s1"])  # başqa açılışın qeydiyyatı
        self.assertFalse(ok)

    def test_wrong_scale_and_invalid_points_are_refused(self):
        ok, message = self._record(max_points="10")
        self.assertFalse(ok)
        self.assertIn("şkalası uyğun gəlmir", message)
        for points in ("0", "6", "4.25", "-1"):
            ok, _message = self._record(points=points)
            self.assertFalse(ok, points)
        self.assertFalse(SelfWorkMark.objects.filter(enrollment=self.enrollment).exists())

    def test_second_award_is_refused_from_any_source(self):
        ok, _message = self._record(slot=1, points="3")
        self.assertTrue(ok)
        ok, message = self._record(slot=1, points="5")
        self.assertFalse(ok)
        self.assertIn("artıq yazılıb (Sərbəst iş 1 · 3/5)", message)
        # Jurnalın özündə (müəllim lövhəsi) yazılmış bal da «birinci bal» sayılır.
        with bypass_rls():
            slot2 = SelfWorkTopic.objects.get(offering=self.offering, slot_index=2)
            self.assertTrue(
                journal_extras.set_selfwork_mark(
                    offering=self.offering, topic_id=slot2.id, enrollment_id=self.enrollment.id, done=True, points="2"
                )
            )
        ok, message = self._record(slot=2, points="4")
        self.assertFalse(ok)
        self.assertIn("2/5", message)

    def test_same_source_ref_is_idempotent_but_different_points_are_not(self):
        ref = _ref()
        self.assertTrue(self._record(ref=ref)[0])
        ok, message = self._record(ref=ref)
        self.assertTrue(ok)
        self.assertTrue(message.startswith("Jurnalda artıq yazılıb"), message)
        self.assertFalse(self._record(ref=ref, points="3")[0])
        self.assertEqual(SelfWorkMark.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_total_never_exceeds_ten(self):
        # Struktur Σ max ≤ 10-u təmin edir; burada ORM ilə ƏLAVƏ slot (Σ 15) qurub müdafiə yoxlanır.
        self.assertTrue(self._record(slot=1, points="5")[0])
        with bypass_rls():
            extra = SelfWorkTopic.objects.create(
                organization=self.org, offering=self.offering, title="Artıq", order=9, slot_index=3, max_points=5
            )
            SelfWorkMark.objects.create(
                organization=self.org, topic=extra, enrollment=self.enrollment, done=True, points=Decimal("5")
            )
        ok, message = self._record(slot=2, points="1")
        self.assertFalse(ok)
        self.assertIn("10 baldan çox ola bilməz", message)

    def test_no_or_mismatched_structure_is_refused(self):
        bare, enrollments = self._fresh_offering(code="SWH2", option=None)
        ok, message = self._record(offering=bare, enrollment=enrollments["swp_s0"])
        self.assertFalse(ok)
        self.assertIn("sərbəst iş strukturu yoxdur", message)
        with bypass_rls():
            approve_syllabus(self.o1, self.teacher, option="2x5")  # 10 qiymətli köhnə mövzu
        ok, message = self._record(offering=self.o1, enrollment=self.e1["swp_s2"])
        self.assertFalse(ok)
        self.assertIn("2 × 5", message)
        self.assertFalse(SelfWorkTopic.objects.filter(offering=self.o1, slot_index__isnull=False).exists())

    def test_board_cannot_change_folder_points_but_documented_correction_can(self):
        ref = _ref()
        self.assertTrue(self._record(slot=1, points="4", ref=ref)[0])
        with bypass_rls():
            slot1 = SelfWorkTopic.objects.get(offering=self.offering, slot_index=1)
            self.assertFalse(
                journal_extras.set_selfwork_mark(
                    offering=self.offering, topic_id=slot1.id, enrollment_id=self.enrollment.id, done=True, points="5"
                ),
                "fənn qovluğu balı lövhədə oxu-only-dir",
            )
            self.assertFalse(journal_extras.delete_selfwork_topic(topic=slot1), "qovluq balı olan mövzu silinmir")
            item_corrections.apply_selfwork_correction(
                offering=self.offering,
                topic=slot1,
                enrollment=self.enrollment,
                new_done=False,
                new_points="",
                reason=CorrectionReason.TECHNICAL,
                note="Plagiat təsdiqləndi — bal ləğv edilir.",
                document=_pdf(),
                by_user=self.teacher,
            )
            mark = SelfWorkMark.objects.get(topic=slot1, enrollment=self.enrollment)
        self.assertEqual((mark.done, mark.points, mark.source, mark.source_ref), (False, None, "subject_folder", ref))
        ok, message = self._record(slot=1, points="4", ref=ref)
        self.assertFalse(ok, "sənədli düzəlişlə silinmiş bal təkrar sinxronla qayıtmır")
        self.assertIn("sənədli düzəlişlə dəyişdirilib", message)

    # ── önbaxış ─────────────────────────────────────────────────────────────
    def _preview(self, **kwargs):
        params = {"offering": self.offering, "enrollment": self.enrollment, "slot_index": 2, "points": Decimal("4")}
        params.update(kwargs)
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            result = hook.preview(**params)
        writes = [
            q["sql"] for q in ctx.captured_queries if q["sql"].split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        ]
        self.assertEqual(writes, [], "önbaxış YAZMIR")
        self.assertLessEqual(len(ctx.captured_queries), 3, [q["sql"][:120] for q in ctx.captured_queries])
        return result

    def test_preview_is_read_only_and_cheap_before_and_after_structure(self):
        before = self._preview()
        self.assertEqual(
            (before["topic_title"], before["max_points"], before["current_points"], before["total_after"]),
            ("Sərbəst iş 2", 5, None, Decimal("4")),
        )
        self.assertFalse(before["blocked"])
        self.assertEqual(before["total_max"], 10)
        self.assertFalse(SelfWorkTopic.objects.filter(offering=self.offering).exists(), "struktur qurulmayıb")
        self.assertTrue(self._record(slot=1, points="3")[0])
        after = self._preview()
        self.assertEqual((after["total_after"], after["blocked"]), (Decimal("7"), False))
        graded = self._preview(slot_index=1)
        self.assertTrue(graded["blocked"])
        self.assertEqual(graded["current_points"], Decimal("3"))
        self.assertIn("artıq yazılıb", graded["reason"])

    def test_preview_without_points_reports_only_journal_state(self):
        """Çekməcə açılanda bal hələ yoxdur — bu «etibarsız bal» deyil; kilid isə yenə görünür."""
        for empty in (None, "", "  "):
            result = self._preview(points=empty)
            self.assertFalse(result["blocked"], result["reason"])
            self.assertEqual((result["max_points"], result["total_after"]), (5, Decimal("0")))
        self.assertTrue(self._preview(points="4,55")["blocked"], "etibarsız yazılış yenə bloklanır")
        with bypass_rls():
            _lock(self.org, self.offering)
        self.assertTrue(self._preview(points=None)["reason"].startswith("Jurnal kilidlidir"))

    def test_preview_reports_lock_and_invalid_points(self):
        self.assertTrue(self._preview(points=Decimal("6"))["blocked"])
        with bypass_rls():
            _lock(self.org, self.offering)
        locked = self._preview()
        self.assertTrue(locked["blocked"])
        self.assertTrue(locked["reason"].startswith("Jurnal kilidlidir"))


@pytest.mark.postgres
class HookConcurrencyTest(SelfWorkLegacyFixture, TransactionTestCase):
    """Paralel iki sinxron (qovluğun on-commit + yenidən-cəhd əmri) → TƏK bal."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        type(self).setUpTestData()
        self.offering, self.enrollments = self._fresh_offering(code="SWC1", option="2x5")

    def _parallel(self, calls):
        barrier = Barrier(len(calls))

        def wrap(kwargs):
            def run():
                close_old_connections()
                try:
                    barrier.wait(timeout=10)
                    with bypass_rls():
                        return hook.record_points(**kwargs)
                finally:
                    close_old_connections()

            return run

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(wrap(kwargs)) for kwargs in calls]
            return [future.result(timeout=60) for future in futures]

    def _kwargs(self, enrollment, *, points="4", ref=None, slot=1):
        return {
            "offering": self.offering,
            "enrollment": enrollment,
            "slot_index": slot,
            "slot_title": "Paralel",
            "max_points": Decimal("5"),
            "points": Decimal(points),
            "source_ref": ref or _ref(),
            "by_user": self.teacher,
        }

    def test_two_different_awards_for_one_slot_leave_exactly_one(self):
        student = self.enrollments["swp_s0"]
        results = self._parallel([self._kwargs(student, points="4"), self._kwargs(student, points="5")])
        self.assertEqual(sorted(ok for ok, _message in results), [False, True], results)
        with bypass_rls():
            marks = list(SelfWorkMark.objects.filter(enrollment=student))
            topics = SelfWorkTopic.objects.filter(offering=self.offering).count()
        self.assertEqual(len(marks), 1)
        self.assertIn(marks[0].points, (Decimal("4"), Decimal("5")))
        self.assertEqual(topics, 2, "paralel ilk bal strukturu İKİ dəfə qurmur")

    def test_parallel_retries_of_the_same_award_are_idempotent(self):
        student = self.enrollments["swp_s1"]
        ref = _ref()
        results = self._parallel([self._kwargs(student, ref=ref), self._kwargs(student, ref=ref)])
        self.assertEqual([ok for ok, _message in results], [True, True], results)
        with bypass_rls():
            self.assertEqual(SelfWorkMark.objects.filter(enrollment=student).count(), 1)

    def test_parallel_first_awards_for_different_students_build_one_structure(self):
        results = self._parallel(
            [self._kwargs(self.enrollments["swp_s2"], slot=1), self._kwargs(self.enrollments["swp_s3"], slot=2)]
        )
        self.assertEqual([ok for ok, _message in results], [True, True], results)
        with bypass_rls():
            self.assertEqual(
                sorted(SelfWorkTopic.objects.filter(offering=self.offering).values_list("slot_index", flat=True)),
                [1, 2],
            )
