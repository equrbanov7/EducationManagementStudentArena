"""Read-only original marks for a placement's exact historical enrollment."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .journal_access import can_edit_journal, can_observe_journal
from .journal_shares import journal_scope
from .language_cohorts import can_manage
from .models import LanguageLevelPlacement, LessonMark


def can_view_source(actor, event, *, scopes=None):
    enrollment = event.source_enrollment
    if enrollment is None:
        return False
    offering = enrollment.offering
    if scopes is None:
        scopes = {}
    if offering.pk not in scopes:
        permitted = can_edit_journal(actor, offering) or can_observe_journal(actor, offering)
        scopes[offering.pk] = journal_scope(actor, offering) if permitted else None
    scope = scopes[offering.pk]
    return scope is not None and scope.allows_enrollment(enrollment.pk)


@login_required
@require_GET
def detail(request, cohort_id, event_id):
    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    event = get_object_or_404(
        LanguageLevelPlacement.objects.select_related(
            "cohort__organization",
            "cohort__offering",
            "source_enrollment__offering__organization",
            "source_enrollment__offering__subject",
            "source_enrollment__offering__period",
            "student",
            "home_group",
        ),
        organization=organization,
        cohort_id=cohort_id,
        pk=event_id,
    )
    if not can_manage(request.user, event.cohort) or not can_view_source(request.user, event):
        raise Http404
    marks = (
        LessonMark.objects.filter(
            organization=organization,
            enrollment=event.source_enrollment,
            enrollment__student_id=event.student_id,
            lesson__organization=organization,
            lesson__offering_id=event.source_enrollment.offering_id,
        )
        .select_related("lesson")
        .order_by("lesson__date", "lesson__start_time", "lesson_id", "pk")
    )
    return render(request, "registrar/language_cohort_history.html", {"event": event, "marks": marks})
