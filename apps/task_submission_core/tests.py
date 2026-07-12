"""
Tests for task_submission_core — assignments/labs/projects modullarının
paylaşdığı submission köməkçiləri. Buradakı funksiyalar əsasən saf məntiqdir,
ona görə DB tələb etməyən SimpleTestCase + sadə fake obyektlərlə yoxlanılır.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from core.helpers import REVIEW_EDIT_LOCK_WINDOW

from .review import (
    annotate_student_review_state,
    build_pagination_query,
    format_input_number,
    parse_filter_date,
    resolve_identity_window,
    resolve_recheck_window,
)
from .services import (
    _clamp_score,
    _resolve_task_max_score,
    attach_submission_file,
    bulk_grade_submissions,
    merge_submission_content,
    parse_score_value,
)


def _submission(status="graded", graded_at=None, grade=None, **extra):
    return SimpleNamespace(status=status, graded_at=graded_at, grade=grade, **extra)


# ---------------------------------------------------------------------------
# services — saf köməkçilər
# ---------------------------------------------------------------------------
class MergeSubmissionContentTest(SimpleTestCase):
    def test_joins_text_and_url(self):
        self.assertEqual(merge_submission_content("cavab", "http://repo.example"), "cavab\nhttp://repo.example")

    def test_strips_and_skips_empty_parts(self):
        self.assertEqual(merge_submission_content("  cavab  ", ""), "cavab")
        self.assertEqual(merge_submission_content("", "  "), "")

    def test_url_only(self):
        self.assertEqual(merge_submission_content("", "http://repo.example"), "http://repo.example")


class ParseScoreValueTest(SimpleTestCase):
    def test_decimal_passthrough(self):
        value = Decimal("7.5")
        self.assertIs(parse_score_value(value), value)

    def test_string_and_int_coerced(self):
        self.assertEqual(parse_score_value("8.25"), Decimal("8.25"))
        self.assertEqual(parse_score_value(9), Decimal("9"))

    def test_invalid_returns_default(self):
        self.assertIsNone(parse_score_value("qeyri-ədəd"))
        self.assertEqual(parse_score_value("bad", default=Decimal("0")), Decimal("0"))
        self.assertIsNone(parse_score_value(None))


class ClampScoreTest(SimpleTestCase):
    """Audit: qiymət [0, max] aralığına salınır."""

    def test_clamps_above_max(self):
        self.assertEqual(_clamp_score(Decimal("150"), 100), Decimal("100"))

    def test_clamps_below_zero(self):
        self.assertEqual(_clamp_score(Decimal("-5"), 100), Decimal("0"))

    def test_within_range_unchanged(self):
        self.assertEqual(_clamp_score(Decimal("42"), 100), Decimal("42"))

    def test_no_max_only_floors_at_zero(self):
        self.assertEqual(_clamp_score(Decimal("-3"), None), Decimal("0"))
        self.assertEqual(_clamp_score(Decimal("999"), None), Decimal("999"))

    def test_none_score_passthrough(self):
        self.assertIsNone(_clamp_score(None, 100))


class ResolveTaskMaxScoreTest(SimpleTestCase):
    def test_resolves_from_assignment(self):
        sub = SimpleNamespace(assignment=SimpleNamespace(max_score=50), project=None)
        self.assertEqual(_resolve_task_max_score(sub), 50)

    def test_resolves_from_project(self):
        sub = SimpleNamespace(project=SimpleNamespace(max_score=80))
        self.assertEqual(_resolve_task_max_score(sub), 80)

    def test_resolves_lab_via_assignment_lab(self):
        # LabSubmission.assignment → LabAssignment.lab.max_score
        lab_assignment = SimpleNamespace(max_score=None, lab=SimpleNamespace(max_score=70))
        sub = SimpleNamespace(assignment=lab_assignment)
        self.assertEqual(_resolve_task_max_score(sub), 70)

    def test_returns_none_when_unresolvable(self):
        self.assertIsNone(_resolve_task_max_score(SimpleNamespace()))


class BulkGradeLengthGuardTest(SimpleTestCase):
    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            bulk_grade_submissions([object()], [1, 2], ["a", "b"], graded_by=None)


class AttachSubmissionFileTest(SimpleTestCase):
    def test_uses_attach_uploaded_file_when_available(self):
        calls = []

        submission = SimpleNamespace(attach_uploaded_file=lambda f, original_name="": calls.append((f, original_name)))
        field = attach_submission_file(submission, "fayl", original_name="orijinal.pdf")

        self.assertEqual(field, "files")
        self.assertEqual(calls, [("fayl", "orijinal.pdf")])

    def test_falls_back_to_file_attribute(self):
        submission = SimpleNamespace(file=None)
        field = attach_submission_file(submission, "fayl")
        self.assertEqual(field, "file")
        self.assertEqual(submission.file, "fayl")


# ---------------------------------------------------------------------------
# review — tarix/format köməkçiləri
# ---------------------------------------------------------------------------
class ParseFilterDateTest(SimpleTestCase):
    def test_valid_date(self):
        raw, parsed = parse_filter_date("2026-07-05")
        self.assertEqual(raw, "2026-07-05")
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 7, 5))

    def test_invalid_or_empty(self):
        self.assertEqual(parse_filter_date("05.07.2026"), ("", None))
        self.assertEqual(parse_filter_date(""), ("", None))
        self.assertEqual(parse_filter_date(None), ("", None))


class FormatInputNumberTest(SimpleTestCase):
    def test_none_and_empty(self):
        self.assertEqual(format_input_number(None), "")
        self.assertEqual(format_input_number(""), "")

    def test_trailing_zeros_trimmed(self):
        self.assertEqual(format_input_number("3.50"), "3.5")
        self.assertEqual(format_input_number("2.00"), "2")

    def test_comma_decimal_normalised(self):
        self.assertEqual(format_input_number("4,25"), "4.25")

    def test_zero_kept(self):
        self.assertEqual(format_input_number("0.0"), "0")
        self.assertEqual(format_input_number(0), "0")


class BuildPaginationQueryTest(SimpleTestCase):
    def test_drops_empty_values(self):
        filters = SimpleNamespace(search_query="", status_filter="all", date_from_raw="", date_to_raw="")
        query = build_pagination_query(filters=filters, selected_submission_id=None)
        self.assertEqual(query, "status=all")

    def test_keeps_filled_values(self):
        filters = SimpleNamespace(
            search_query="elvin", status_filter="graded", date_from_raw="2026-07-01", date_to_raw=""
        )
        query = build_pagination_query(
            filters=filters,
            selected_submission_id=7,
            from_section="labs",
            return_to="/geri/",
        )
        self.assertIn("q=elvin", query)
        self.assertIn("status=graded", query)
        self.assertIn("date_from=2026-07-01", query)
        self.assertIn("submission=7", query)
        self.assertIn("from_section=labs", query)
        self.assertNotIn("date_to", query)


# ---------------------------------------------------------------------------
# review — pəncərə məntiqi (recheck / identity / student görünüşü)
# ---------------------------------------------------------------------------
class ResolveRecheckWindowTest(SimpleTestCase):
    def test_not_graded_returns_closed(self):
        self.assertEqual(resolve_recheck_window(_submission(status="submitted")), (False, 0))

    def test_graded_without_timestamp_returns_closed(self):
        self.assertEqual(resolve_recheck_window(_submission(graded_at=None)), (False, 0))

    def test_inside_window_returns_remaining_seconds(self):
        now = timezone.now()
        submission = _submission(graded_at=now - timedelta(seconds=60))
        is_open, seconds_left = resolve_recheck_window(submission, current_time=now)
        self.assertTrue(is_open)
        expected = int(REVIEW_EDIT_LOCK_WINDOW.total_seconds()) - 60
        self.assertEqual(seconds_left, expected)

    def test_after_window_returns_closed(self):
        now = timezone.now()
        submission = _submission(graded_at=now - REVIEW_EDIT_LOCK_WINDOW - timedelta(seconds=1))
        self.assertEqual(resolve_recheck_window(submission, current_time=now), (False, 0))


class ResolveIdentityWindowTest(SimpleTestCase):
    """Tanınmayan model adı → təşkilat açarı yoxdur → yalnız status/pəncərə qaydası."""

    def test_ungraded_identity_stays_hidden(self):
        submission = _submission(status="submitted", _meta=SimpleNamespace(model_name="other"))
        self.assertEqual(resolve_identity_window(submission), (True, 0))

    def test_identity_revealed_after_lock_window(self):
        now = timezone.now()
        submission = _submission(
            graded_at=now - REVIEW_EDIT_LOCK_WINDOW,
            _meta=SimpleNamespace(model_name="other"),
        )
        self.assertEqual(resolve_identity_window(submission, current_time=now), (False, 0))

    def test_identity_hidden_inside_lock_window(self):
        now = timezone.now()
        submission = _submission(
            graded_at=now - timedelta(seconds=30),
            _meta=SimpleNamespace(model_name="other"),
        )
        hidden, seconds_left = resolve_identity_window(submission, current_time=now)
        self.assertTrue(hidden)
        self.assertEqual(seconds_left, int(REVIEW_EDIT_LOCK_WINDOW.total_seconds()) - 30)


class AnnotateStudentReviewStateTest(SimpleTestCase):
    def test_graded_after_window_shows_review_data(self):
        now = timezone.now()
        submission = _submission(grade=Decimal("9"), graded_at=now - REVIEW_EDIT_LOCK_WINDOW)
        (annotated,) = annotate_student_review_state([submission], current_time=now)
        self.assertTrue(annotated.has_grade)
        self.assertTrue(annotated.show_review_data)
        self.assertEqual(annotated.review_available_in_seconds, 0)

    def test_graded_inside_window_hides_review_with_countdown(self):
        now = timezone.now()
        submission = _submission(grade=Decimal("9"), graded_at=now - timedelta(seconds=10))
        (annotated,) = annotate_student_review_state([submission], current_time=now)
        self.assertFalse(annotated.show_review_data)
        self.assertEqual(
            annotated.review_available_in_seconds,
            int(REVIEW_EDIT_LOCK_WINDOW.total_seconds()) - 10,
        )

    def test_ungraded_submission_has_no_grade_flags(self):
        submission = _submission(status="submitted", grade=None)
        (annotated,) = annotate_student_review_state([submission])
        self.assertFalse(annotated.has_grade)
        self.assertFalse(annotated.show_review_data)
        self.assertEqual(annotated.review_available_in_seconds, 0)
