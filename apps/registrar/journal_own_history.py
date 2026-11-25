"""Own authored journal evidence: a narrow read-only fallback after unassignment.

This never grants normal journal observation, student roster/finals/export access,
or write permission. Only explicitly authored lessons and own entered cells are
returned, with live same-tenant grade.input authority required on every request.

Owner 2026-11-26: the page is a journal-like grid (students × the teacher's lessons) plus a
«when / where» lessons table (:mod:`apps.registrar.journal_own_history_grid`). A viewer who may
already open the full journal read-only can see the same subset for another teacher
(``?own_history=1&teacher=<id>``, «Müəllimin yazdığı hissə»).
"""

from django.db.models import Exists, OuterRef, Q
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


def can_view_teacher_part(request, offering) -> bool:
    """Another teacher's authored part: the viewer opens the FULL journal (editor / corrector / roster manager /
    observer) AND is not narrowed by a kind/row-limited share — a seminar-only share holder must not see the
    lecturer's lessons or another section's students through this page (same rule as ``journal_reviewed_history``)."""
    from .journal_access import can_open_journal
    from .journal_shares import journal_scope

    return can_open_journal(request, offering) and journal_scope(request.user, offering).full


def gate_list_links(request, offerings) -> None:
    """Broad journal list: «Müəllimin yazdığı hissə» only where :func:`can_view_teacher_part` holds."""
    for offering in offerings:
        if getattr(offering, "journal_teacher_history_id", None) and (
            request is None or not can_view_teacher_part(request, offering)
        ):
            offering.journal_teacher_history_id = None


def _subject(request, offering):
    """``(teacher, broad)`` — whose authored part is shown.

    No ``teacher`` param (or the viewer's own id): the viewer's own history, behind live ``grade.input`` authority.
    Another teacher's id (owner 2026-11-26, «Müəllimin yazdığı hissə»): only for a viewer who may already open the
    FULL, unnarrowed journal (:func:`can_view_teacher_part`); the subset can never show more than that viewer already
    sees. Anyone else gets 404.
    """
    raw = (request.GET.get("teacher") or "").strip()
    if not raw or raw == str(request.user.pk):
        if not eligible(request.user, offering.organization):
            raise Http404
        return request.user, False
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        raise Http404
    from django.contrib.auth import get_user_model

    if pk <= 0 or not can_view_teacher_part(request, offering):
        raise Http404
    teacher = get_user_model().objects.filter(pk=pk).first()
    if teacher is None:
        raise Http404
    return teacher, True


def _back_url(request, teacher, broad) -> str:
    """Same-site relative ``/jurnal/…`` ``next`` only; otherwise the history list (with the teacher filter)."""
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme

    list_url = reverse("registrar:journal_list")
    raw = request.GET.get("next") or ""
    if raw.startswith(list_url) and "\\" not in raw and url_has_allowed_host_and_scheme(raw, allowed_hosts=None):
        return raw
    return f"{list_url}?teaching=history" + (f"&teacher={teacher.pk}" if broad else "")


def _tab_url(base: dict, kind: str) -> str:
    from django.utils.http import urlencode

    return "?" + urlencode({**base, **({"kind": kind} if kind else {})})


def detail(request, offering):
    """The detail access gate delegates here only when normal journal access failed (or ``?own_history=1``)."""
    request_org = getattr(request, "organization", None)
    if request.method != "GET" or request_org is None or request_org.pk != offering.organization_id:
        raise Http404
    teacher, broad = _subject(request, offering)
    from .journal_own_history_grid import build, load_lessons

    lessons = load_lessons(
        recorded_lessons(teacher).filter(organization=offering.organization, offering=offering), offering, teacher
    )
    if not lessons:
        raise Http404
    # Owner 2026-11-17: lesson time / «Yazılıb» moments are staff-only — never on the teacher's own view.
    from .journal_lesson_timing import show_lesson_timing

    timing = broad and show_lesson_timing(request.user, offering)
    context = build(offering, teacher, lessons, kind=(request.GET.get("kind") or "").strip(), timing=timing)
    back = _back_url(request, teacher, broad)
    base = {"own_history": "1", **({"teacher": teacher.pk} if broad else {})}
    if request.GET.get("next") and back == request.GET.get("next"):
        base["next"] = back
    context["kind_tabs"] = [{**tab, "url": _tab_url(base, tab["value"])} for tab in context["kind_tabs"]]
    context.update(
        offering=offering,
        subject_teacher=teacher,
        subject_name=teacher.get_full_name() or teacher.username,
        broad_view=broad,
        all_tab_url=_tab_url(base, ""),
        back_url=back,
    )
    return render(request, "registrar/journal_own_history.html", context)
