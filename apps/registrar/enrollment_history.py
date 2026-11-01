"""Exact supersession history; source_group describes provenance, not eligibility."""

from django.db.models import Exists, F, OuterRef

from .models import Enrollment


def predecessors():
    """Fail closed even for old/imported pointers which bypassed model clean()."""
    return Enrollment.objects.filter(
        status=Enrollment.Status.DROPPED,
        superseded_by__isnull=False,
        organization_id=F("superseded_by__organization_id"),
        offering__organization_id=F("organization_id"),
        student_id=F("superseded_by__student_id"),
        offering__subject_id=F("superseded_by__offering__subject_id"),
        offering__period_id=F("superseded_by__offering__period_id"),
        superseded_by__offering__organization_id=F("organization_id"),
    ).exclude(pk=F("superseded_by_id"))


def annotate_predecessor(queryset):
    return queryset.annotate(has_exact_predecessor=Exists(predecessors().filter(superseded_by_id=OuterRef("pk"))))
