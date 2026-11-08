"""Permission-checked historical records, without changing current journals or totals."""

import datetime
from urllib.parse import urlencode

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.tenancy import get_request_organization, request_has_active_organization_context

from . import guest_roster, journal_access
from . import journal_reviewed_history_spec as fixed
from . import journal_shares
from .models import CourseOffering, Enrollment, LessonMark


def _can_open(request, offering):
    return (
        journal_access.can_edit_journal(request.user, offering)
        or journal_access.can_observe_journal(request.user, offering)
        or journal_access.can_correct_offering(request, offering)
        or guest_roster.can_manage_offering_roster(request.user, offering)
    )


def _identity(offering, group):
    return (
        str(offering.organization_id) == fixed.ORG
        and str(offering.subject_id) == fixed.SUBJECT
        and str(offering.period_id) == fixed.PERIOD
        and str(offering.group_id) == group
        and offering.instructor_id == fixed.TEACHER
        and offering.is_active
        and not offering.is_intensive
    )


def _reviewed(request, source, *, kind=""):
    spec = fixed.PAIRS.get(str(source.pk))
    org = get_request_organization(request)
    if (
        spec is None
        or org is None
        or str(org.pk) != fixed.ORG
        or not request_has_active_organization_context(request)
        or not request.user.is_authenticated
        or not request.user.is_active
        or kind not in ("", "lecture", "seminar")
        or not _identity(source, spec["source_group"])
        or not _can_open(request, source)
    ):
        return None
    target = (
        CourseOffering.objects.filter(organization_id=fixed.ORG, pk=spec["target"])
        .select_related("organization", "group", "subject", "period")
        .first()
    )
    if target is None or not _identity(target, spec["target_group"]) or not _can_open(request, target):
        return None
    # A link must not widen a row/kind-limited share into a historical roster.
    if (
        not journal_shares.journal_scope(request.user, source).full
        or not journal_shares.journal_scope(request.user, target).full
    ):
        return None
    enrolled = {
        row.student_id: row
        for row in Enrollment.objects.filter(
            organization_id=fixed.ORG, offering=target, pk__in=[p[0] for p in spec["students"].values()]
        ).select_related("superseded_by")
    }
    if set(enrolled) != set(spec["students"]):
        return None
    for uid, (historical_id, current_id) in spec["students"].items():
        row = enrolled[uid]
        if str(row.pk) != historical_id:
            return None
        if spec["mode"] == "superseded":
            successor = row.superseded_by
            if (
                row.status != Enrollment.Status.DROPPED
                or successor is None
                or str(successor.pk) != current_id
                or successor.student_id != uid
                or successor.organization_id != source.organization_id
                or successor.offering_id != source.pk
                or successor.status != Enrollment.Status.ENROLLED
                or successor.superseded_by_id is not None
            ):
                return None
        elif row.status != Enrollment.Status.ENROLLED or row.superseded_by_id is not None:
            return None
    UserProfile = apps.get_model("accounts.UserProfile")
    if UserProfile.objects.filter(organization_id=fixed.ORG, user_id__in=enrolled).count() != len(enrolled):
        return None
    marks = LessonMark.objects.filter(
        organization_id=fixed.ORG,
        enrollment_id__in=[row.pk for row in enrolled.values()],
        lesson__organization_id=fixed.ORG,
        lesson__offering=target,
        lesson__date__gte=source.period.start_date,
        lesson__date__lte=min(source.period.end_date, datetime.date.fromisoformat(fixed.UNTIL)),
        lesson__kind__in=[kind] if kind else ["lecture", "seminar"],
    )
    if set(marks.values_list("enrollment__student_id", flat=True)) != set(enrolled):
        return None
    return {"source": source, "target": target, "marks": marks, "student_count": len(enrolled), "kind": kind}


def notice(request, source, *, kind=""):
    reviewed = _reviewed(request, source, kind=kind)
    if reviewed is None:
        return None
    target = reviewed["target"]
    url = reverse("registrar:reviewed_journal_history", args=[source.pk])
    if kind:
        url += "?" + urlencode({"kind": kind})
    return {
        "url": url,
        "journal_label": f"{target.group.name} · {target.subject.name}",
        "student_count": reviewed["student_count"],
    }


def detail_context(request, offering, context):
    from .journal_provenance import history_context

    return {
        "journal_history": history_context(offering, context["journal"]),
        "reviewed_history_notice": (
            notice(request, offering, kind=context.get("journal_kind", ""))
            if context.get("active_tab") == "grid"
            else None
        ),
    }


@login_required
@require_GET
def detail(request, offering_id):
    source = journal_access.offering_or_404(request, offering_id)
    reviewed = _reviewed(request, source, kind=request.GET.get("kind", ""))
    if reviewed is None:
        raise Http404
    marks = (
        reviewed["marks"]
        .select_related("lesson", "enrollment__student", "entered_by")
        .order_by("lesson__date", "lesson__start_time", "lesson_id", "enrollment__student__last_name", "enrollment_id")
    )
    # A fixed 17/25-person cohort, bounded to the reviewed historical period.
    rows = list(marks[:1001])
    if len(rows) > 1000:
        raise Http404
    return render(request, "registrar/reviewed_journal_history.html", {**reviewed, "rows": rows})
