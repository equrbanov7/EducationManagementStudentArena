"""Own authored journal evidence: a narrow read-only fallback after unassignment.

This never grants normal journal observation, student roster/finals/export access,
or write permission. Only explicitly authored lessons and own entered cells are
returned, with live same-tenant grade.input authority required on every request.
"""

from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from .models import Lesson, LessonMark


def eligible(user, organization):
    if not organization or not organization.is_active or not user.is_authenticated or not user.is_active:
        return False
    from .integrity import is_authorized_instructor
    from .journal_access import _snapshot_grade_input

    snapshot = _snapshot_grade_input(user, organization)
    return snapshot if snapshot is not None else is_authorized_instructor(organization=organization, instructor=user)


def recorded_lessons(user):
    marks = LessonMark.objects.filter(
        organization_id=OuterRef("organization_id"), lesson_id=OuterRef("pk"), entered_by=user
    )
    return (
        Lesson.objects.filter(date__lte=timezone.localdate())
        .annotate(_own_mark=Exists(marks))
        .filter(Q(instructor=user) | Q(created_by=user) | Q(_own_mark=True))
    )


def offering_ids(user, organization):
    if not eligible(user, organization):
        return Lesson.objects.none().values("offering_id")
    return recorded_lessons(user).filter(organization=organization).values("offering_id")


def detail(request, offering):
    """The detail access gate delegates here only when normal journal access failed."""
    if request.method != "GET" or not eligible(request.user, offering.organization):
        raise Http404
    lessons = recorded_lessons(request.user).filter(organization=offering.organization, offering=offering)
    if not lessons.exists():
        raise Http404
    from django.core.paginator import Paginator

    marks = LessonMark.objects.filter(organization=offering.organization, entered_by=request.user).select_related(
        "enrollment__student"
    )
    lessons = lessons.order_by("date", "start_time", "pk").prefetch_related(
        Prefetch("marks", queryset=marks, to_attr="author_marks")
    )
    page = Paginator(lessons, 20).get_page(request.GET.get("page"))
    return render(request, "registrar/journal_own_history.html", {"offering": offering, "page_obj": page})
