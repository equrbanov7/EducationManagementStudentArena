"""Bounded, permission-scoped choices for language cohort management."""

from types import SimpleNamespace

from django.db.models import Q

from core.search_text import tolerant_q

from . import guest_roster, language_cohorts
from .journal_access import can_edit_journal, can_observe_journal
from .journal_list_scope import journal_list_base
from .journal_shares import own_or_shared_q
from .language_levels import LEVEL_RE, level_family, level_of
from .models import AcademicStatus, CourseOffering, Enrollment, StudentAcademicRecord


def existing_level_journals(user, organization):
    queryset, _broad = journal_list_base(user, SimpleNamespace(organization=organization))
    queryset = CourseOffering.objects.filter(organization=organization, is_active=True).filter(
        Q(pk__in=queryset.values("pk")) | own_or_shared_q(user)
    )
    # Səviyyə fənləri DB-də süzülür (2026-11-01): korrektor/koordinator üçün əhatə
    # BÜTÜN jurnallardır (1700+) — hamısını çəkib Python-da yoxlamaq səhifəni ləngidirdi.
    # `level_of` dəqiq qaydası (yazı variantları) yenə Python-da təsdiqlənir.
    return [
        row
        for row in queryset.filter(
            organization=organization, language_cohort__isnull=True, subject__name__iregex=LEVEL_RE.pattern
        )
        .select_related("subject", "group", "period", "instructor", "organization")
        .order_by("subject__name", "group__name")
        if level_of(row.subject.name) and (can_edit_journal(user, row) or can_observe_journal(user, row))
    ]


def candidate_records(*, cohort, actor, query=""):
    # Staff source-home-group scope OR existing course/enrollment scope. A
    # teacher's grade.input permission never opens the whole tenant directory.
    source_ids = set()
    offerings = (
        CourseOffering.objects.filter(organization=cohort.organization, period_id=cohort.period_id, is_active=True)
        .filter(Q(instructor=actor) | Q(shares__teacher=actor, shares__is_active=True))
        .select_related("subject", "organization")
        .distinct()
    )
    for offering in offerings:
        if level_of(offering.subject.name) and level_family(offering.subject.name) == cohort.family:
            for enrollment in Enrollment.objects.filter(
                organization=cohort.organization, offering=offering, status=Enrollment.Status.ENROLLED
            ).select_related("offering__organization"):
                if language_cohorts.source_access(actor, enrollment):
                    source_ids.add(enrollment.student_id)
    removed = (
        Enrollment.objects.filter(
            organization=cohort.organization,
            offering=cohort.offering,
            status=Enrollment.Status.DROPPED,
            level_departures__cohort=cohort,
            level_departures__action="remove",
        )
        .select_related("offering__organization")
        .distinct()
    )
    for enrollment in removed:
        if language_cohorts.source_access(actor, enrollment):
            source_ids.add(enrollment.student_id)
    records = StudentAcademicRecord.objects.filter(
        organization=cohort.organization,
        group__organization=cohort.organization,
        group__language_cohort__isnull=True,
        group__is_active=True,
        is_active=True,
        status=AcademicStatus.ENROLLED,
        student__is_active=True,
        student__profile__organization=cohort.organization,
        student__profile__access_state="active",
        student__memberships__organization=cohort.organization,
        student__memberships__is_active=True,
        student__memberships__role__organization=cohort.organization,
        student__memberships__role__is_active=True,
    ).filter(Q(group__in=guest_roster.scoped_group_queryset(actor, cohort.organization)) | Q(student_id__in=source_ids))
    # Dözümlü axtarış (core.search_text, sahib 2026-11-11): registr, az↔ing hərfləri, söz sırası; qrup kod rejimində.
    search_q = tolerant_q(
        query,
        ("student__first_name", "student__last_name", "student__profile__patronymic"),
        compact_fields=("group__name",),
    )
    if search_q is not None:
        records = records.filter(search_q)
    records = records.exclude(
        student_id__in=Enrollment.objects.filter(
            organization=cohort.organization, offering=cohort.offering, status=Enrollment.Status.ENROLLED
        ).values("student_id")
    )
    return (
        records.select_related("student", "student__profile", "group")
        .distinct()
        .order_by("student__last_name", "student__first_name", "pk")[:50]
    )
