"""Source-aware review predicates; historical evidence is never rewritten.

The 50-point rule is established for ordinary legacy journals, not every raw
attempt. Historical language/Level exceptions are documented in
``docs/migration/reports/SUBHELI_BALLAR_2026-09-03.md`` §2/§5. Unknown scales
remain review candidates rather than being labelled corrupt scores.
"""

from decimal import Decimal

from django.db.models import Q

from .language_levels import LEVEL_RE
from .models import LegacyGradeEvidenceKind

LEGACY_ENTRY_MAX = Decimal("50")
LEGACY_EXAM_MAX = Decimal("50")
LEGACY_RESIT_MAX = Decimal("50")
LEGACY_FINAL_MAX = Decimal("100")


def _known_sources() -> Q:
    return Q(source_system="myedu_mariadb") & (
        Q(source_table="yekun", evidence_kind=LegacyGradeEvidenceKind.SUMMARY)
        | Q(
            source_table__in=("journals_dates_points", "journals_dates_points_archive"),
            evidence_kind__in=(LegacyGradeEvidenceKind.EXAM, LegacyGradeEvidenceKind.RESIT),
        )
    )


def _language_scale() -> Q:
    name = "enrollment__offering__subject__name__iregex"
    return Q(legacy_level__gt=0) | Q(**{name: f"xarici dil|akademik kommunikasiya|level|{LEVEL_RE.pattern}"})


def _known_fifty_scale() -> Q:
    return (
        _known_sources()
        & Q(enrollment__offering__assessment_scheme__entry_score_max=50)
        & ~Q(enrollment__offering__subject__name="")
        & ~_language_scale()
        # A summary without the source's Level marker does not establish its scale.
        & (Q(legacy_level=0) | ~Q(evidence_kind=LegacyGradeEvidenceKind.SUMMARY))
    )


def _component_above_fifty() -> Q:
    return Q(entry_score__gt=LEGACY_ENTRY_MAX) | Q(exam_score__gt=LEGACY_EXAM_MAX) | Q(resit_score__gt=LEGACY_RESIT_MAX)


def out_of_range_condition() -> Q:
    """Hard 0..100 bound, plus the verified ordinary-journal 0..50 rule."""
    condition = _known_fifty_scale() & _component_above_fifty()
    for field in ("entry_score", "exam_score", "resit_score", "final_score"):
        condition |= Q(**{f"{field}__lt": 0}) | Q(**{f"{field}__gt": LEGACY_FINAL_MAX})
    return condition


def unknown_scale_condition() -> Q:
    """A 50..100 value alone is not proof of corruption or an appeal loss."""
    return (
        _component_above_fifty()
        & ~(_known_fifty_scale() | (_known_sources() & _language_scale()))
        & ~out_of_range_condition()
    )
