"""statistics_selectors paketi — _shared."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model

User = get_user_model()

_ZERO = Decimal("0")


def _safe_pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round(float(numerator) * 100 / float(denominator), 1)


def _safe_avg(values):
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else 0.0


def _parse_date(raw):
    """Parse a YYYY-MM-DD string to a date object, or None."""
    from datetime import date as _date

    if not raw:
        return None
    try:
        return _date.fromisoformat(str(raw).strip())
    except (ValueError, TypeError):
        return None


def _apply_date_filter(qs, field_name, date_from, date_to):
    if date_from:
        qs = qs.filter(**{f"{field_name}__date__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{field_name}__date__lte": date_to})
    return qs


def _content_type_enabled(selected_type, expected_type):
    return selected_type in ("all", expected_type)


def build_ai_stats_payload(*, role, stats):
    """Build a concise stats dict suitable for the AI prompt.

    This strips internal keys and keeps only the data the AI model
    needs to reason about, preventing prompt bloat.
    """
    payload = {
        "role": role,
        "summary": stats.get("summary", {}),
    }
    if "trend" in stats:
        payload["trend"] = stats["trend"]
    if "group_comparison" in stats:
        payload["group_comparison"] = stats["group_comparison"][:10]
    if "score_breakdown" in stats:
        payload["score_breakdown"] = stats["score_breakdown"]
    if "org_comparison" in stats:
        payload["org_comparison"] = stats["org_comparison"][:10]
    if "course_rankings" in stats:
        payload["course_rankings"] = stats["course_rankings"][:10]
    return payload


UNSUPPORTED_METRICS = """
The following metrics were requested but are NOT supported by the current
data model and were intentionally skipped:

Student:
  - Strongest/weakest topics: QuestionBlock is available on exams but not
    linked uniformly across assignments/labs/projects. Partial exam-block
    analysis is possible but not cross-content-type.
  - Comparison to class/group average: Possible for exams via StudentGroup
    but not uniformly across all content types.
  - Live exam answer totals: Live players are semi-anonymous and are not
    reliably linked to a user account, so student dashboards must not show
    organization-level live aggregates.
  - Video watch time / attendance / login heatmaps: No model support.

Teacher:
  - Proctoring incident trends: ProctoringLog exists but SupervisionIncident
    aggregation per teacher is not directly linked; would require joining
    through exams + attempts. Deferred to future iteration.
  - At-risk students (automatic detection): Requires ML scoring or
    threshold-based rules not currently defined.

Organization Admin:
  - Grading SLA: No SLA target field exists on any model.
  - Workload distribution: Requires submission-per-teacher tracking which
    is partially possible but not reliably complete.

Superadmin:
  - Adoption/activity trends by country: Organization has country FK but
    activity (logins, daily active users) is not tracked.
  - Anomaly detection: Requires statistical baselines not currently stored.
  - Grading delays: Possible for assignments (submitted_at vs graded_at)
    but not uniformly for exams/labs/projects.

All roles:
  - AcademicPeriod / OrgUnit filtering: Models exist but content (exams,
    courses, etc.) does not consistently reference them. Filter UI is
    present but may return no results for orgs that don't use periods/units.
  - Radar/scatter charts for topic analysis: Deferred due to lack of
    uniform topic tagging across content types.
"""
