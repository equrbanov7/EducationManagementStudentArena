"""GET-only discovery of two canonical owned journals with anonymous legacy authors.

Existing canonical ownership and live grade.input authority remain necessary.
This is not a workload assignment, an authorship claim, or a write grant.
"""

import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Q
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.tenancy import get_request_organization, request_has_active_organization_context

from . import journal_master_history_spec as fixed
from .journal_own_history import eligible
from .models import CourseOffering, LessonMark


def identity_q(user, organization):
    """A fixed identity predicate; it only narrows an already-authorized queryset."""
    if organization is None or str(organization.pk) != fixed.ORG or user.pk != fixed.TEACHER:
        return Q(pk__in=[])
    identities = Q(pk__in=[])
    for offering_id, group_id in fixed.OFFERINGS.items():
        identities |= Q(pk=offering_id, group_id=group_id)
    return (
        identities
        & Q(
            organization_id=fixed.ORG,
            instructor_id=fixed.TEACHER,
            subject_id=fixed.SUBJECT,
            subject__organization_id=fixed.ORG,
            period_id=fixed.PERIOD,
            period__organization_id=fixed.ORG,
            group__organization_id=fixed.ORG,
            group__is_active=True,
            group__unit_type="group",
            group__settings__degree_level="master",
            is_active=True,
        )
        & ~Q(course_format="intensive")
    )


def historical_marks():
    return LessonMark.objects.filter(
        organization_id=fixed.ORG,
        lesson__organization_id=fixed.ORG,
        enrollment__organization_id=fixed.ORG,
        enrollment__offering_id=OuterRef("pk"),
        lesson__offering_id=OuterRef("pk"),
        lesson__date__gte=OuterRef("period__start_date"),
        lesson__date__lte=datetime.date.fromisoformat(fixed.UNTIL),
    )


def attach(offering, *, kind=""):
    """The list projection already proved exact identity and historical mark evidence."""
    if getattr(offering, "journal_is_current_load", False) or not getattr(offering, "journal_is_master_history", False):
        return
    url = reverse("registrar:master_owned_journal_history", args=[offering.pk])
    offering.journal_entry_url = url + (f"?kind={kind}" if kind in ("lecture", "seminar", "lab") else "")


@login_required
@require_GET
def detail(request, offering_id):
    from django.core.paginator import Paginator
    from django.db.models import Exists

    from .teacher_journal_list import project

    organization = get_request_organization(request)
    kind = request.GET.get("kind", "")
    if (
        not request_has_active_organization_context(request)
        or not eligible(request.user, organization)
        or kind not in ("", "lecture", "seminar", "lab")
    ):
        raise Http404
    candidates = project(
        CourseOffering.objects.filter(identity_q(request.user, organization), pk=offering_id),
        request.user,
        organization,
    )
    offering = (
        candidates.filter(journal_is_current_load=False)
        .annotate(_has_history=Exists(historical_marks()))
        .filter(_has_history=True)
        .select_related("organization", "subject", "group", "period")
        .first()
    )
    if offering is None:
        raise Http404
    marks = LessonMark.objects.filter(
        organization=organization,
        lesson__organization=organization,
        lesson__offering=offering,
        enrollment__organization=organization,
        enrollment__offering=offering,
        lesson__date__gte=offering.period.start_date,
        lesson__date__lte=datetime.date.fromisoformat(fixed.UNTIL),
    )
    if kind:
        marks = marks.filter(lesson__kind=kind)
    marks = marks.select_related("lesson", "enrollment__student", "entered_by").order_by(
        "lesson__date", "lesson__start_time", "lesson_id", "enrollment__student__last_name", "enrollment_id"
    )
    return render(
        request,
        "registrar/master_owned_journal_history.html",
        {"offering": offering, "page_obj": Paginator(marks, 100).get_page(request.GET.get("page"))},
    )
