"""Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi — növbə, qərar, düzəliş.

Bu testlərin əsas iddiası ÜÇ MADDƏLİDİR:

1. **Növbə sübut qatından doğulur** — kateqoriya siyahısı ``LegacyGradeMappingStatus``
   enum-undan və faktın xam sütunlarından çıxır; kodda dondurulmuş sətir siyahısı
   yoxdur. Enum genişlənsə növbə də genişlənir.
2. **Köhnə sətir HEÇ VAXT dəyişmir** — təsdiq də, düzəliş də YALNIZ yeni sətir
   yaradır; ``LegacyGradeFact`` append-only qalır.
3. **Qapılar fail-closed-dır** — tenant sərhədi, struktur əhatəsi və sənəd tələbi
   üç ayrı qatda saxlanılır.
"""

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.organizations.models import Organization
from apps.registrar import finals, grading_scale
from apps.registrar import legacy_grade_review as review_read
from apps.registrar import legacy_grade_review_actions as review_write
from apps.registrar import legacy_grade_review_rows as rows_read
from apps.registrar.models import (
    CorrectionReason,
    ExamScoreEntry,
    ExamScoreEntryKind,
    FinalGrade,
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LegacyGradeMappingStatus,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from core.constants import OrganizationType
from core.rls import bypass_rls

_SNAPSHOT = "a" * 64
_ROW_HASH = "b" * 64
_DIGEST = "c" * 64


def _pdf(name="tesdiq.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class _ReviewSetup(_BaseJournalSetup):
    """Bir bağlı, bir bağlanmamış fakt — növbənin iki əsas halı."""

    maxDiff = None

    def _fact(self, **kwargs):
        defaults = {
            "organization": self.org,
            "enrollment": self.enrollment,
            "source_system": "myedudb",
            "source_table": "yekun",
            "source_pk": 1,
            "source_snapshot_sha256": _SNAPSHOT,
            "source_row_hash": _ROW_HASH,
            "materialization_digest": _DIGEST,
            "transform_version": "legacy-grade-v1",
            "evidence_kind": LegacyGradeEvidenceKind.SUMMARY,
            "mapping_status": LegacyGradeMappingStatus.LINKED,
            "mapping_issue_code": "",
            "source_student_ref": "student-1",
            "source_journal_ref": "journal-1",
            "source_enrollment_ref": "journal-1:student-1",
        }
        defaults.update(kwargs)
        if defaults["mapping_status"] not in (
            LegacyGradeMappingStatus.LINKED,
            LegacyGradeMappingStatus.CONFLICT,
        ):
            defaults["enrollment"] = None
            defaults["source_enrollment_ref"] = ""
        with bypass_rls():
            return LegacyGradeFact.objects.create(**defaults)

    def _other_org(self):
        owner = type(self.owner).objects.create_user("lgr_owner_b", "lgr-owner-b@example.test", "pw")
        with bypass_rls():
            return Organization.objects.create(
                name="LGR B",
                slug="lgr-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )


class CategoryDerivationTests(_ReviewSetup):
    def test_source_bounds_match_the_importer_rule(self):
        """Hədlər köçürmə qaydası ilə EYNİ olmalıdır — dublikat testlə kilidlənir.

        ``registrar`` modul-sərhəd qaydasına görə ``legacy_import``-u import edə
        bilmir, ona görə dəyərlər orada yazılıb burada yoxlanılır. Bu test yeganə
        yerdir ki, hər iki tərəfi eyni anda görür (testlər sərhəd gate-indən azaddır).
        """
        from apps.legacy_import.services import rehearsal_legacy_grade_facts_source as importer

        # İmporterin öz qaydası: sərhədə BƏRABƏR dəyər problem SAYILMIR,
        # bir addım yuxarısı isə sayılır.
        self.assertEqual(importer._score_range_rules(entry=review_read.LEGACY_ENTRY_MAX), ())
        self.assertEqual(importer._score_range_rules(exam=review_read.LEGACY_EXAM_MAX), ())
        self.assertEqual(importer._score_range_rules(resit=review_read.LEGACY_RESIT_MAX), ())
        self.assertEqual(importer._score_range_rules(final=review_read.LEGACY_FINAL_MAX), ())
        self.assertNotEqual(importer._score_range_rules(entry=review_read.LEGACY_ENTRY_MAX + 1), ())
        self.assertNotEqual(importer._score_range_rules(exam=review_read.LEGACY_EXAM_MAX + 1), ())
        self.assertNotEqual(importer._score_range_rules(resit=review_read.LEGACY_RESIT_MAX + 1), ())
        self.assertNotEqual(importer._score_range_rules(final=review_read.LEGACY_FINAL_MAX + 1), ())
        self.assertEqual(review_read.LEGACY_RESIT_MAX, review_read.LEGACY_EXAM_MAX)

    def test_every_non_linked_mapping_status_becomes_a_category(self):
        """Kateqoriyalar enum-dan doğulur — sabit siyahı yoxdur."""
        codes = {spec.code for spec in review_read.category_specs(self.org)}
        for status in LegacyGradeMappingStatus:
            if status == LegacyGradeMappingStatus.LINKED:
                self.assertNotIn(str(status.value), codes, "sağlam hal növbəyə düşməməlidir")
            else:
                self.assertIn(str(status.value), codes, f"{status.value} enum üzvünün kateqoriyası yoxdur")

    def test_clean_linked_fact_is_not_in_the_queue(self):
        self._fact(exam_score_text="30", exam_score=Decimal("30"))
        self.assertEqual(review_read.review_queue(organization=self.org).count(), 0)

    def test_out_of_range_uses_the_raw_value_and_keeps_it_unrounded(self):
        self._fact(
            final_score_text="117",
            final_score=Decimal("117"),
            entry_score_text="59",
            entry_score=Decimal("59"),
        )
        queue = review_read.review_queue(organization=self.org, categories=[review_read.CATEGORY_OUT_OF_RANGE])
        self.assertEqual(queue.count(), 1)

        prepared = rows_read.prepared_page_queryset(review_read.review_queue(organization=self.org), self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        # Xam dəyər GÖRÜNƏN qalır: clamp də, round da yoxdur.
        self.assertEqual(row["final_score"], "117")
        self.assertEqual(row["entry_score"], "59")
        self.assertEqual(row["severity"], review_read.Severity.CRITICAL)

    def test_live_mismatch_compares_the_fact_with_the_live_final_grade(self):
        """K11 — köçürmənin dəqiqliyi; heç bir bal DÜSTURU qurulmur."""
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=Decimal("10"), by_user=self.admin)
        self._fact(exam_score_text="17", exam_score=Decimal("17"))

        queue = review_read.review_queue(organization=self.org, categories=[review_read.CATEGORY_LIVE_MISMATCH])
        self.assertEqual(queue.count(), 1)

        prepared = rows_read.prepared_page_queryset(queue, self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        self.assertEqual(row["exam_score"], "17")
        self.assertEqual(row["live_exam_score"], "10.00")
        self.assertTrue(row["is_live"])

    def test_matching_live_score_leaves_the_row_out_of_the_queue(self):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=Decimal("17"), by_user=self.admin)
        self._fact(exam_score_text="17", exam_score=Decimal("17"))
        self.assertEqual(
            review_read.review_queue(organization=self.org, categories=[review_read.CATEGORY_LIVE_MISMATCH]).count(),
            0,
        )

    def test_failed_with_exam_score_follows_the_tenant_letter_scale(self):
        """Kəsilmə həddi SABİT 51 deyil — universitetin öz şkalasından gəlir."""
        self._fact(
            final_score_text="40",
            final_score=Decimal("40"),
            exam_score_text="20",
            exam_score=Decimal("20"),
        )
        code = review_read.CATEGORY_FAILED_WITH_EXAM
        self.assertEqual(review_read.review_queue(organization=self.org, categories=[code]).count(), 1)

        # Şkalanı elə dəyiş ki, 40 artıq keçid sayılsın → kateqoriya SÖNSÜN.
        with bypass_rls():
            grading_scale.set_bands(self.org, [[31, "E", "2.00"], [0, "F", "0.00"]])
            self.org.refresh_from_db()
        self.assertEqual(review_read.pass_threshold(self.org), Decimal("31"))
        self.assertEqual(review_read.review_queue(organization=self.org, categories=[code]).count(), 0)

    def test_unlinked_fact_is_queued_and_cannot_be_corrected(self):
        self._fact(
            mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
            mapping_issue_code="legacy_grade_fact_unresolved",
            exam_score_text="30",
            exam_score=Decimal("30"),
        )
        queue = review_read.review_queue(organization=self.org)
        self.assertEqual(queue.count(), 1)
        prepared = rows_read.prepared_page_queryset(queue, self.org)
        row = rows_read.serialize_page(list(prepared), self.org, can_correct=True)[0]
        # Düzəlişin hədəfi yoxdur → səth düyməni GÖSTƏRMİR (səssiz 403 əvəzinə).
        self.assertFalse(row["can_correct"])
        self.assertEqual(row["enrollment_id"], "")

    def test_queue_never_crosses_the_tenant_boundary(self):
        other = self._other_org()
        self._fact(final_score_text="117", final_score=Decimal("117"))
        self.assertEqual(review_read.review_queue(organization=self.org).count(), 1)
        self.assertEqual(review_read.review_queue(organization=other).count(), 0)

    def test_severity_ordering_puts_the_worst_row_first(self):
        self._fact(
            source_pk=1,
            mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
            mapping_issue_code="legacy_grade_fact_unresolved",
        )
        self._fact(source_pk=2, final_score_text="117", final_score=Decimal("117"))
        queue = review_read.review_queue(organization=self.org)
        ordered = rows_read.order_by_severity(rows_read.prepared_page_queryset(queue, self.org), self.org)
        rows = rows_read.serialize_page(list(ordered), self.org)
        self.assertEqual(rows[0]["severity"], review_read.Severity.CRITICAL)
        self.assertEqual(rows[-1]["severity"], review_read.Severity.WATCH)


class ReviewDecisionTests(_ReviewSetup):
    def test_verify_writes_a_review_and_leaves_the_fact_untouched(self):
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        before = LegacyGradeFact.objects.get(pk=fact.pk)

        with bypass_rls():
            review = review_write.record_decision(
                organization=self.org,
                fact_id=str(fact.pk),
                action="verify",
                note="Kağız jurnalla tutuşduruldu.",
                actor=self.admin,
            )

        self.assertEqual(review.decision, LegacyGradeReviewDecision.VERIFIED)
        self.assertEqual(review.reason_code, review_write.REASON_VERIFIED)
        self.assertEqual(len(review.evidence_digest), 64)
        after = LegacyGradeFact.objects.get(pk=fact.pk)
        self.assertEqual(after.final_score_text, before.final_score_text)
        self.assertEqual(after.final_score, before.final_score)

    def test_dispute_requires_a_note(self):
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        with bypass_rls():
            with self.assertRaises(ValidationError):
                review_write.record_decision(
                    organization=self.org,
                    fact_id=str(fact.pk),
                    action="dispute",
                    note="  ",
                    actor=self.admin,
                )
        self.assertEqual(LegacyGradeReview.objects.filter(fact=fact).count(), 0)

    def test_review_status_moves_the_row_between_status_filters(self):
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        pending = review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_PENDING})
        self.assertEqual(pending.count(), 1)

        with bypass_rls():
            review_write.record_decision(
                organization=self.org, fact_id=str(fact.pk), action="verify", note="ok", actor=self.admin
            )

        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_PENDING}).count(), 0
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_VERIFIED}).count(), 1
        )
        self.assertEqual(
            review_read.progress(organization=self.org),
            {
                "total": 1,
                "reviewed": 1,
                "pending": 0,
                "percent": 100,
            },
        )

    def test_progress_denominator_ignores_the_status_filter(self):
        """«Baxılmayıb» seçiləndə məxrəc daralmamalıdır — yoxsa faiz həmişə 0 olar."""
        self._fact(source_pk=1, final_score_text="117", final_score=Decimal("117"))
        fact = self._fact(source_pk=2, final_score_text="118", final_score=Decimal("118"))
        with bypass_rls():
            review_write.record_decision(
                organization=self.org, fact_id=str(fact.pk), action="verify", note="ok", actor=self.admin
            )
        result = review_read.progress(organization=self.org, filters={"status": review_read.STATUS_PENDING})
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["percent"], 50)

    def test_actor_without_the_exam_centre_key_cannot_decide(self):
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        with bypass_rls():
            with self.assertRaises(PermissionDenied):
                review_write.record_decision(
                    organization=self.org,
                    fact_id=str(fact.pk),
                    action="verify",
                    note="ok",
                    actor=self.teacher,
                )
        self.assertEqual(LegacyGradeReview.objects.filter(fact=fact).count(), 0)

    def test_decision_is_refused_for_a_fact_from_another_tenant(self):
        other = self._other_org()
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        with bypass_rls():
            with self.assertRaises(ValidationError):
                review_write.record_decision(
                    organization=other, fact_id=str(fact.pk), action="verify", note="ok", actor=self.admin
                )


class CorrectionBridgeTests(_ReviewSetup):
    def _seed_live_score(self, value="10"):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=Decimal(value), by_user=self.admin)

    def test_correction_goes_through_the_existing_audited_exam_score_flow(self):
        self._seed_live_score("10")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))

        with bypass_rls():
            result = review_write.apply_correction(
                organization=self.org,
                fact_id=str(fact.pk),
                score="17",
                reason=CorrectionReason.TECHNICAL,
                note="Kağız imtahan vərəqi ilə yoxlandı.",
                evidence=_pdf(),
                actor=self.admin,
            )

        entry = result["entry"]
        self.assertIsInstance(entry, ExamScoreEntry)
        # Mövcud axın işə düşüb: bu bir DÜZƏLİŞ sətridir, ilkin daxiletmə deyil.
        self.assertEqual(entry.kind, ExamScoreEntryKind.CORRECTION)
        self.assertEqual(entry.old_score, Decimal("10.00"))
        self.assertEqual(entry.new_score, Decimal("17"))
        self.assertTrue(entry.evidence)

        review = result["review"]
        self.assertEqual(review.decision, LegacyGradeReviewDecision.VERIFIED)
        self.assertEqual(review.reason_code, review_write.REASON_CORRECTED)
        self.assertIn("→", review.note)

        # Köhnə sətir toxunulmaz qalıb.
        after = LegacyGradeFact.objects.get(pk=fact.pk)
        self.assertEqual(after.exam_score_text, "17")
        self.assertEqual(after.exam_score, Decimal("17"))
        # Canlı bal isə dəyişib — dəqiqləşdirmə məhz oraya yazılır.
        self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("17.00"))

    def test_correction_without_a_document_is_rejected_and_writes_nothing(self):
        """Sənəd tələbi servis qatındadır; qərar sətri də YAZILMAMALIDIR."""
        self._seed_live_score("10")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))

        with bypass_rls():
            with self.assertRaises(ValidationError):
                review_write.apply_correction(
                    organization=self.org,
                    fact_id=str(fact.pk),
                    score="17",
                    reason=CorrectionReason.TECHNICAL,
                    note="Sənədsiz cəhd.",
                    evidence=None,
                    actor=self.admin,
                )

        self.assertEqual(LegacyGradeReview.objects.filter(fact=fact).count(), 0)
        self.assertEqual(ExamScoreEntry.objects.filter(enrollment=self.enrollment).count(), 0)
        self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("10.00"))

    def test_correction_that_changes_nothing_is_refused(self):
        self._seed_live_score("17")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))
        with bypass_rls():
            with self.assertRaises(ValidationError):
                review_write.apply_correction(
                    organization=self.org,
                    fact_id=str(fact.pk),
                    score="17",
                    reason=CorrectionReason.TECHNICAL,
                    note="Eyni dəyər.",
                    evidence=_pdf(),
                    actor=self.admin,
                )
        self.assertEqual(LegacyGradeReview.objects.filter(fact=fact).count(), 0)

    def test_unlinked_fact_cannot_be_corrected(self):
        fact = self._fact(
            mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
            mapping_issue_code="legacy_grade_fact_unresolved",
            exam_score_text="30",
            exam_score=Decimal("30"),
        )
        with bypass_rls():
            with self.assertRaises(ValidationError):
                review_write.apply_correction(
                    organization=self.org,
                    fact_id=str(fact.pk),
                    score="30",
                    reason=CorrectionReason.TECHNICAL,
                    note="Sahibi yoxdur.",
                    evidence=_pdf(),
                    actor=self.admin,
                )

    def test_corrected_row_reports_the_corrected_status_not_verified(self):
        self._seed_live_score("10")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))
        with bypass_rls():
            review_write.apply_correction(
                organization=self.org,
                fact_id=str(fact.pk),
                score="17",
                reason=CorrectionReason.TECHNICAL,
                note="Düzəldildi.",
                evidence=_pdf(),
                actor=self.admin,
            )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_CORRECTED}).count(),
            1,
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_VERIFIED}).count(),
            0,
        )

    def test_progress_denominator_survives_the_correction(self):
        """Düzəliş məxrəci kiçiltməməlidir — «N-dən M-i baxılıb» geriyə sürüşməsin.

        `live_exam_mismatch` canlı `FinalGrade`-dən doğulur: düzəliş tətbiq
        olunan an şərt pozulur. Kateqoriya möhürü olmasaydı sətir növbədən tamam
        çıxar, sayğac isə «1-dən 0-ı» → «0-dan 0-ı» kimi mənasız oxunardı.
        """
        self._seed_live_score("10")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))
        before = review_read.progress(organization=self.org)
        self.assertEqual((before["total"], before["reviewed"]), (1, 0))

        with bypass_rls():
            review_write.apply_correction(
                organization=self.org,
                fact_id=str(fact.pk),
                score="17",
                reason=CorrectionReason.TECHNICAL,
                note="Düzəldildi.",
                evidence=_pdf(),
                actor=self.admin,
            )

        after = review_read.progress(organization=self.org)
        self.assertEqual((after["total"], after["reviewed"], after["percent"]), (1, 1, 100))

    def test_correction_required_then_corrected_keeps_category_and_history(self):
        """Son düzəliş statusu dəyişir, amma ilkin sual və qərar tarixçəsi itmir."""
        self._seed_live_score("10")
        fact = self._fact(exam_score_text="17", exam_score=Decimal("17"))
        stamp = review_read.encode_category_codes((review_read.CATEGORY_LIVE_MISMATCH,))
        with bypass_rls():
            LegacyGradeReview.objects.create(
                organization=self.org,
                fact=fact,
                decision=LegacyGradeReviewDecision.CORRECTION_REQUIRED,
                reason_code=review_write.REASON_DISPUTED,
                note="Düzəliş tələb olunur.",
                evidence_digest="d" * 64,
                reviewed_by=self.admin,
                category_codes=stamp,
            )
            review_write.apply_correction(
                organization=self.org,
                fact_id=str(fact.pk),
                score="17",
                reason=CorrectionReason.TECHNICAL,
                note="Kağız imtahan vərəqi ilə düzəldildi.",
                evidence=_pdf(),
                actor=self.admin,
            )

        history = list(LegacyGradeReview.objects.filter(fact=fact))
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].decision, LegacyGradeReviewDecision.CORRECTION_REQUIRED)
        self.assertEqual(history[1].reason_code, review_write.REASON_CORRECTED)
        self.assertIn(
            review_read.CATEGORY_LIVE_MISMATCH,
            review_read.decode_category_codes(history[1].category_codes),
        )
        prepared = rows_read.prepared_page_queryset(review_read.review_queue(organization=self.org), self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        self.assertEqual(row["review"]["status"], review_read.STATUS_CORRECTED)
        self.assertEqual(row["review"]["history_count"], 2)
        self.assertEqual(
            review_read.review_queue(
                organization=self.org,
                categories=(review_read.CATEGORY_LIVE_MISMATCH,),
                filters={"status": review_read.STATUS_CORRECTED},
            ).count(),
            1,
        )
        other = self._other_org()
        self.assertEqual(
            review_read.review_queue(
                organization=other,
                categories=(review_read.CATEGORY_LIVE_MISMATCH,),
                filters={"status": review_read.STATUS_CORRECTED},
            ).count(),
            0,
        )

    def test_category_stamp_does_not_leak_into_a_neighbouring_category(self):
        """Möhür kateqoriya-DƏQİQ-dir: başqa səbəbdən düzəldilmiş sətir sızmır."""
        # Bu fakt YALNIZ diapazon kateqoriyasındadır: canlı bal yoxdur, ona görə
        # `live_exam_mismatch` şərti heç vaxt doğru olmayıb.
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        with bypass_rls():
            review_write.record_decision(
                organization=self.org, fact_id=str(fact.pk), action="verify", note="Kağızla yoxlandı.", actor=self.admin
            )
        stamped = LegacyGradeReview.objects.get(fact=fact)
        self.assertEqual(
            review_read.decode_category_codes(stamped.category_codes),
            (review_read.CATEGORY_OUT_OF_RANGE,),
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, categories=(review_read.CATEGORY_LIVE_MISMATCH,)).count(),
            0,
        )

    def test_review_history_is_append_only_across_two_decisions(self):
        fact = self._fact(final_score_text="117", final_score=Decimal("117"))
        with bypass_rls():
            review_write.record_decision(
                organization=self.org, fact_id=str(fact.pk), action="dispute", note="Kağız lazımdır.", actor=self.admin
            )
            review_write.record_decision(
                organization=self.org, fact_id=str(fact.pk), action="verify", note="Tapıldı.", actor=self.admin
            )
        self.assertEqual(LegacyGradeReview.objects.filter(fact=fact).count(), 2)

        prepared = rows_read.prepared_page_queryset(review_read.review_queue(organization=self.org), self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        self.assertEqual(row["review"]["history_count"], 2)
        self.assertEqual(row["review"]["status"], review_read.STATUS_VERIFIED)
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_VERIFIED}).count(),
            1,
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"status": review_read.STATUS_DISPUTED}).count(),
            0,
        )


class QueueFilterTests(_ReviewSetup):
    def test_structural_filter_narrows_to_the_group_subtree(self):
        self._fact(final_score_text="117", final_score=Decimal("117"))
        matched = review_read.review_queue(organization=self.org, filters={"group": str(self.group.pk)})
        self.assertEqual(matched.count(), 1)

    def test_unknown_structural_id_yields_an_empty_queue_not_everything(self):
        """Tanınmayan id fail-OPEN olmamalıdır."""
        self._fact(final_score_text="117", final_score=Decimal("117"))
        stray = review_read.review_queue(
            organization=self.org,
            filters={"group": "00000000-0000-0000-0000-000000000000"},
        )
        self.assertEqual(stray.count(), 0)

    def test_search_matches_the_legacy_student_reference(self):
        self._fact(final_score_text="117", final_score=Decimal("117"), source_student_ref="student-1")
        self.assertEqual(review_read.review_queue(organization=self.org, filters={"q": "student-1"}).count(), 1)
        self.assertEqual(review_read.review_queue(organization=self.org, filters={"q": "student-9"}).count(), 0)

    def test_category_counts_expose_every_category_even_when_empty(self):
        self._fact(final_score_text="117", final_score=Decimal("117"))
        rows = review_read.category_counts(organization=self.org)
        codes = {row["code"]: row for row in rows}
        self.assertEqual(codes[review_read.CATEGORY_OUT_OF_RANGE]["total"], 1)
        self.assertEqual(codes[review_read.CATEGORY_LIVE_MISMATCH]["total"], 0)
        for row in rows:
            self.assertIn(row["severity"], review_read.SEVERITY_ORDER)
            self.assertTrue(row["label"])
            self.assertTrue(row["hint"])

    def test_teacher_and_period_filters_use_the_offering(self):
        self._fact(final_score_text="117", final_score=Decimal("117"))
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"teacher": str(self.teacher.pk)}).count(), 1
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"period": str(self.period.pk)}).count(), 1
        )
        self.assertEqual(
            review_read.review_queue(organization=self.org, filters={"teacher": str(self.student.pk)}).count(), 0
        )


class QueueSanityTests(_ReviewSetup):
    def test_a_row_can_carry_several_categories_at_once(self):
        """Şiddət ƏN PİS haldan gəlir, ortalamadan yox."""
        with bypass_rls():
            finals.set_exam_score(enrollment=self.enrollment, score=Decimal("10"), by_user=self.admin)
        self._fact(
            mapping_status=LegacyGradeMappingStatus.CONFLICT,
            mapping_issue_code="legacy_grade_fact_conflict",
            exam_score_text="70",
            exam_score=Decimal("70"),
        )
        prepared = rows_read.prepared_page_queryset(review_read.review_queue(organization=self.org), self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        codes = {category["code"] for category in row["categories"]}
        self.assertIn("conflict", codes)
        self.assertIn(review_read.CATEGORY_OUT_OF_RANGE, codes)
        self.assertIn(review_read.CATEGORY_LIVE_MISMATCH, codes)
        self.assertEqual(row["severity"], review_read.Severity.CRITICAL)

    def test_recorded_at_and_source_reference_reach_the_row(self):
        self._fact(
            final_score_text="117",
            final_score=Decimal("117"),
            legacy_recorded_at_text=str(datetime.date(2023, 1, 17)),
        )
        prepared = rows_read.prepared_page_queryset(review_read.review_queue(organization=self.org), self.org)
        row = rows_read.serialize_page(list(prepared), self.org)[0]
        self.assertEqual(row["recorded_at"], "2023-01-17")
        self.assertEqual(row["source_reference"], "yekun #1")
