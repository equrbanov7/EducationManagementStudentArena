"""Sorğu qurucusu (2026-09-30) — «Sorğular» inbox-u (kabinet bölməsi ``surveys-inbox``, ``/sorgu/``
səhifəsi) və sidebar sayğacı (``public.inbox_badge_count``).

Inbox: istifadəçinin auditoriyasında olduğu dərc olunmuş / bağlı ümumi sorğular — «Gözləyən»
(son tarix, məcburilik nişanı, keç/möhlət imkanı), «Tamamlanmış», «Bağlı» (buraxılmış) — və
tələbə üçün semestr sonu müəllim qiymətləndirməsi kampaniyası (bir bənd, irəliləyişlə).
Planlaşdırılmış (hələ açılmamış) sorğu göstərilmir. View-as altında inbox boşdur.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from ..constants import GatePolicy, SurveyKind, SurveyStatus
from .audience import audience_families, role_families, user_in_audience
from .gate_snapshot import active_entries, active_survey_entries
from .survey_respond import defer_active

INBOX_LIMIT = 100


def _memberships(user, organization):
    Membership = django_apps.get_model("organizations", "Membership")
    return list(
        Membership.objects.filter(user=user, organization=organization, is_active=True).select_related(
            "role", "scope_unit"
        )
    )


def _request_memberships(request):
    memberships = getattr(request, "org_memberships", None)
    if memberships is None:
        memberships = _memberships(request.user, request.organization)
    return memberships


def _surveys_for(organization, user, memberships):
    from ..models import Survey

    families = role_families(memberships)
    if not families:
        return []
    base = Survey.objects.filter(
        organization=organization, status__in=[SurveyStatus.PUBLISHED, SurveyStatus.CLOSED]
    ).exclude(kind=SurveyKind.TEACHER_EVALUATION)
    rows = list(base.order_by("-opens_on", "-created_at")[:INBOX_LIMIT])
    # Təhlükəsizlik baxışı 2026-09-30 (L7): qapının yoxladığı AKTİV sorğu limitdən kənarda
    # qalsa istifadəçi doldurma linki olmadan bağlanardı — aktivlər həmişə daxildir.
    seen = {str(survey.pk) for survey in rows}
    missing = [entry["id"] for entry in active_survey_entries(organization, timezone.localdate())]
    missing = [survey_id for survey_id in missing if survey_id not in seen]
    if missing:
        rows.extend(base.filter(pk__in=missing))
    return [
        survey
        for survey in rows
        if audience_families(survey.audience) & families and user_in_audience(survey, user, memberships)
    ]


def _campaign_item(request, today):
    state = getattr(request.user, "_survey_gate_state", None)
    if state is None or not state.total:
        return None
    entries = active_entries(request.organization, today)
    closes = [entry["closes_on"] for entry in entries if entry["closes_on"]]
    return {
        "pending": state.pending,
        "total": state.total,
        "done": state.total - state.pending,
        "closes_on": min(closes) if closes else None,
        "mandatory": any(entry["mandatory"] for entry in entries),
        "url": reverse("surveys:home"),
    }


def build_inbox(request, today=None) -> dict:
    from ..models import SurveyGateSkip, SurveyParticipation

    today = today or timezone.localdate()
    empty = {"pending": [], "completed": [], "closed": [], "campaign": None, "view_as": False}
    organization = getattr(request, "organization", None)
    user = getattr(request, "user", None)
    if getattr(request, "is_view_as", False):
        return {**empty, "view_as": True}
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return empty
    surveys = _surveys_for(organization, user, _request_memberships(request))
    ids = [survey.pk for survey in surveys]
    done = dict(
        SurveyParticipation.objects.filter(survey_id__in=ids, user=user).values_list("survey_id", "completed_on")
    )
    skipped = set(SurveyGateSkip.objects.filter(survey_id__in=ids, user=user).values_list("survey_id", flat=True))
    result = {**empty, "campaign": _campaign_item(request, today)}
    for survey in surveys:
        status = survey.effective_status(today)
        if status == "scheduled":
            continue
        item = {
            "survey": survey,
            "url": reverse("surveys:take", args=[survey.pk]),
            "completed_on": done.get(survey.pk),
            "status": status,
        }
        if survey.pk in done:
            result["completed"].append(item)
        elif status == SurveyStatus.PUBLISHED:
            grace = survey.grace_until
            item.update(
                can_skip=survey.mandatory and survey.gate_policy == GatePolicy.SKIP_ONCE and survey.pk not in skipped,
                skipped=survey.pk in skipped,
                can_defer=bool(
                    survey.mandatory
                    and survey.gate_policy == GatePolicy.DEFER_DAYS
                    and grace
                    and today <= grace
                    and not defer_active(request, survey.pk)
                ),
                grace_until=grace,
                days_left=(survey.closes_on - today).days if survey.closes_on else None,
            )
            result["pending"].append(item)
        else:
            result["closed"].append(item)
    result["pending"].sort(key=lambda item: (not item["survey"].mandatory, item["survey"].closes_on or today))
    return result


# ── Sidebar sayğacı ─────────────────────────────────────────────────────────


def _generic_pending(user, organization, memberships, today) -> int:
    from ..models import Survey, SurveyParticipation

    rows = getattr(user, "_survey_generic_state", None)
    if rows is not None:
        return sum(1 for row in rows if row["eligible"] and not row["done"])
    families = role_families(memberships)
    entries = [e for e in active_survey_entries(organization, today) if audience_families(e["audience"]) & families]
    if not entries:
        return 0
    ids = [entry["id"] for entry in entries]
    done = {
        str(pk)
        for pk in SurveyParticipation.objects.filter(survey_id__in=ids, user=user).values_list("survey_id", flat=True)
    }
    return sum(
        1
        for survey in Survey.objects.filter(organization=organization, pk__in=[pk for pk in ids if pk not in done])
        if user_in_audience(survey, user, memberships)
    )


def _campaign_pending(user, organization, memberships, today) -> bool:
    state = getattr(user, "_survey_gate_state", None)
    if state is not None:
        return bool(state.pending)
    entries = active_entries(organization, today)
    if not entries:
        return False
    from ..models import SurveyCampaign
    from .gate import is_student_account
    from .targets import pending_counts

    if not is_student_account(memberships):
        return False
    campaigns = SurveyCampaign.objects.filter(organization=organization, pk__in=[entry["id"] for entry in entries])
    return any(pending_counts(campaign, user)[0] for campaign in campaigns)


def inbox_badge_count(user, organization) -> int:
    """Doldurulmalı sorğu sayı (kampaniya bir bənd sayılır). Request-ömürlü keşlə, aktiv sorğu
    yoxdursa SIFIR sorğu; kabinet yolunda qapı middleware-inin vəziyyətini təkrar istifadə edir."""
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return 0
    memo = getattr(user, "_survey_inbox_badge", None)
    if isinstance(memo, tuple) and memo[0] == organization.pk:
        return memo[1]
    today = timezone.localdate()
    count = 0
    if active_entries(organization, today) or active_survey_entries(organization, today):
        memberships = None

        def _members():
            nonlocal memberships
            if memberships is None:
                memberships = _memberships(user, organization)
            return memberships

        needs_campaign = getattr(user, "_survey_gate_state", None) is None and active_entries(organization, today)
        needs_generic = getattr(user, "_survey_generic_state", None) is None
        count += int(_campaign_pending(user, organization, _members() if needs_campaign else None, today))
        count += _generic_pending(user, organization, _members() if needs_generic else None, today)
    try:
        user._survey_inbox_badge = (organization.pk, count)
    except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
        pass
    return count
