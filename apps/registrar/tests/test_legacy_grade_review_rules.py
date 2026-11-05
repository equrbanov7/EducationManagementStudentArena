"""Historical score scales are evidence, not a universal 50-point assumption."""

from decimal import Decimal

from apps.registrar import gradebook
from apps.registrar import legacy_grade_review as review
from apps.registrar import legacy_grade_review_rows as rows
from apps.registrar.models import LegacyGradeEvidenceKind
from core.rls import bypass_rls

from .test_legacy_grade_review import _ReviewSetup


class HistoricalScaleTests(_ReviewSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)

    def _source_fact(self, **kwargs):
        defaults = {"source_system": "myedu_mariadb", "legacy_level": 0}
        defaults.update(kwargs)
        return self._fact(**defaults)

    def _count(self, code):
        return review.review_queue(organization=self.org, categories=[code]).count()

    def test_known_ordinary_fifty_point_source_still_flags_overflow(self):
        self._source_fact(exam_score=Decimal("51"))
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 1)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 0)

    def test_known_final_and_resit_cells_retain_the_fifty_point_rule(self):
        for index, kind in enumerate((LegacyGradeEvidenceKind.EXAM, LegacyGradeEvidenceKind.RESIT), 1):
            field = "exam_score" if kind == LegacyGradeEvidenceKind.EXAM else "resit_score"
            self._source_fact(
                source_pk=index,
                source_table="journals_dates_points",
                evidence_kind=kind,
                legacy_level=None,
                **{field: Decimal("51")},
            )
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 2)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 0)

    def test_known_level_source_accepts_historical_hundred_point_score(self):
        self._source_fact(legacy_level=1, exam_score=Decimal("100"), resit_score=Decimal("91"))
        self.assertEqual(review.review_queue(organization=self.org).count(), 0)

    def test_named_language_exception_does_not_inherit_ordinary_fifty_cap(self):
        with bypass_rls():
            self.subject.name = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
            self.subject.save(update_fields=["name"])
        self._source_fact(exam_score=Decimal("70"))
        self.assertEqual(review.review_queue(organization=self.org).count(), 0)

    def test_hard_bound_applies_even_to_level_sources(self):
        for index, field in enumerate(("entry_score", "exam_score", "resit_score", "final_score"), 1):
            self._source_fact(source_pk=index, legacy_level=1, **{field: Decimal("101")})
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 4)

    def test_negative_values_are_never_an_unknown_scale(self):
        self._fact(exam_score=Decimal("-1"))
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 1)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 0)

    def test_unknown_attempt_scale_stays_in_review_without_corruption_claim(self):
        self._source_fact(
            source_table="imthngrscxsblr",
            evidence_kind=LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT,
            legacy_level=None,
            exam_score_text="91",
            exam_score=Decimal("91"),
        )
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 0)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 1)
        query = rows.prepared_page_queryset(review.review_queue(organization=self.org), self.org)
        row = rows.serialize_page(list(query), self.org)[0]
        self.assertEqual(row["exam_score"], "91")
        self.assertEqual(row["severity"], review.Severity.WATCH)

    def test_missing_level_marker_does_not_establish_summary_scale(self):
        self._source_fact(legacy_level=None, exam_score=Decimal("70"))
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 0)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 1)

    def test_unknown_source_cannot_claim_the_known_level_exception(self):
        self._fact(legacy_level=1, exam_score=Decimal("70"))
        self.assertEqual(self._count(review.CATEGORY_OUT_OF_RANGE), 0)
        self.assertEqual(self._count(review.CATEGORY_SCALE_UNKNOWN), 1)
