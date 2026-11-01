"""Exact cohort syllabus constraints expressed inside the existing single query."""

from django.apps import apps
from django.db.models import Exists, Q, Subquery


def rules(*, organization, offering_id):
    cohort = apps.get_model("registrar", "LanguageLevelCohort").objects.filter(
        organization=organization,
        offering_id=offering_id,
    )
    subject = Subquery(cohort.values("offering__subject_id")[:1])
    period = Subquery(cohort.values("period_id")[:1])
    teacher = Subquery(cohort.values("offering__instructor_id")[:1])
    source = Q(
        offering_id=Subquery(cohort.values("source_offering_id")[:1]),
        approved_version__isnull=False,
        offering__organization=organization,
        offering__subject_id=subject,
        offering__period_id=period,
        offering__instructor_id=teacher,
    )
    exact = Q(subject_id=subject, period_id=period, author_id=teacher) & (Q(offering_id=offering_id) | source)
    metadata = {f"_lc_{kind}": Subquery(cohort.values(f"{kind}_hours")[:1]) for kind in ("lecture", "seminar", "lab")}
    metadata["_lc_period"] = Subquery(cohort.values("period_id")[:1])
    return Exists(cohort), exact, source, metadata


def valid_result(syllabus, offering_id):
    if getattr(syllabus, "_lc_period", None) is None or syllabus.offering_id == offering_id:
        return True
    version = syllabus.approved_version
    if (
        version is None
        or version.status != "approved"
        or version.applies_to_period_id not in (None, syllabus._lc_period)
    ):
        return False
    hours = version.plan_hours or {}
    if not isinstance(hours, dict):
        return False
    for kind in ("lecture", "seminar", "lab"):
        value = hours.get(kind, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value != getattr(syllabus, f"_lc_{kind}"):
            return False
    return True
