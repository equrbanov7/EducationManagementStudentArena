"""Tələbə səthi — ``/sorgu/`` (kabinet qabığından KƏNAR, müstəqil səhifə).

Axın: siyahı (müəllim kartları, «2 / 5») → hər müəllim üçün bir səhifəlik forma →
ümumi bölmə → «təşəkkür» → kabinet açılır. View-as altında səth BAĞLIDIR (aktor
tələbənin adından nə doldura, nə də kimi qiymətləndirdiyini görə bilər).
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from ..constants import Section
from ..defaults import LIKERT_LABELS, SCALE_ANCHORS, TEXT_PRIVACY_HINT
from ..forms import field_name, validate_answers
from ..models import SurveyCampaign
from ..services.gate import deferral_active, is_student_account, set_deferral, store_counts
from ..services.gate_snapshot import active_entries, snapshot_is_stale, sync_gate_snapshot
from ..services.submit import AlreadySubmitted, SubmissionClosed, submit_target
from ..services.targets import find_target, next_pending, student_targets
from ..services.templates import template_questions

_CTX = "surveys.student"


def _unavailable(request, reason, status=403):
    return render(request, "surveys/unavailable.html", {"reason": reason}, status=status)


def _guard(request):
    """``(organization, None)`` və ya ``(None, cavab)`` — view-as / tələbə olmayan / org-suz."""
    if getattr(request, "is_view_as", False):
        return None, _unavailable(request, "view_as")
    organization = getattr(request, "organization", None)
    if organization is None:
        return None, _unavailable(request, "no_org", status=404)
    if not is_student_account(getattr(request, "org_memberships", None)):
        return None, _unavailable(request, "not_student")
    return organization, None


def _active_campaigns(organization):
    entries = active_entries(organization, timezone.localdate())
    ids = [entry["id"] for entry in entries]
    campaigns = {
        str(c.pk): c
        for c in SurveyCampaign.objects.filter(organization=organization, pk__in=ids).select_related("period")
    }
    return [campaigns[pk] for pk in ids if pk in campaigns]


def _campaign_or_none(organization, campaign_id):
    try:
        campaign_id = uuid.UUID(str(campaign_id))
    except (TypeError, ValueError, AttributeError):
        return None
    campaign = (
        SurveyCampaign.objects.filter(organization=organization, pk=campaign_id)
        .select_related("period", "template")
        .first()
    )
    if campaign is None or not campaign.is_active_on(timezone.localdate()):
        return None
    return campaign


def _remember(request, organization, campaign, targets):
    pending = sum(1 for target in targets if not target.done)
    store_counts(request, organization, {str(campaign.pk): [pending, len(targets)]})


@login_required
def home(request):
    organization, denied = _guard(request)
    if denied:
        return denied
    today = timezone.localdate()
    if snapshot_is_stale(organization):
        # Xülasə başqa yazı ilə əzilibsə (bax gate_snapshot sənədi) — bərpa (1 sorğu).
        sync_gate_snapshot(organization)
    blocks = []
    for campaign in _active_campaigns(organization):
        targets = student_targets(campaign, request.user, with_labels=True)
        _remember(request, organization, campaign, targets)
        if not targets:
            continue
        done = sum(1 for target in targets if target.done)
        pending = len(targets) - done
        blocks.append(
            {
                "campaign": campaign,
                "targets": [t for t in targets if not t.is_general],
                "general": next((t for t in targets if t.is_general), None),
                "done": done,
                "total": len(targets),
                "pending": pending,
                "next": next_pending(targets),
                "can_defer": bool(
                    pending
                    and campaign.mandatory
                    and campaign.grace_applies_on(today)
                    and not deferral_active(request, campaign.pk, today)
                ),
                "teachers_left": sum(1 for t in targets if not t.done and not t.is_general),
            }
        )
    return render(request, "surveys/home.html", {"blocks": blocks, "today": today})


def _question_rows(questions, values=None, errors=None):
    values, errors = values or {}, errors or {}
    likert = [(score, pgettext("surveys.scale", label)) for score, label in LIKERT_LABELS]
    rows = []
    for question in questions:
        rows.append(
            {
                "question": question,
                "name": field_name(question),
                "text": question.display_text,
                "help": question.display_help_text,
                "value": values.get(question.code, ""),
                "error": errors.get(question.code, ""),
                "choices": likert if question.kind == "likert5" else list(range(1, 11)),
            }
        )
    return rows


def _form_context(campaign, target, questions, targets, values=None, errors=None):
    done = sum(1 for t in targets if t.done)
    return {
        "campaign": campaign,
        "target": target,
        "rows": _question_rows(questions, values, errors),
        "errors": errors or {},
        "position": done + 1,
        "total": len(targets),
        "done": done,
        "scale_low": pgettext("surveys.scale", SCALE_ANCHORS[0]),
        "scale_high": pgettext("surveys.scale", SCALE_ANCHORS[1]),
        "privacy_hint": pgettext("surveys.question", TEXT_PRIVACY_HINT),
    }


def _handle_form(request, organization, campaign, *, scope, offering_id=None, teacher_id=None):
    targets = student_targets(campaign, request.user, with_labels=True)
    target = find_target(targets, scope=scope, offering_id=offering_id, teacher_id=teacher_id)
    if target is None:
        messages.info(request, pgettext(_CTX, "Bu forma sizin üçün açıq deyil."))
        return redirect("surveys:home")
    if target.done:
        messages.info(request, pgettext(_CTX, "Bu sorğunu artıq doldurmusunuz."))
        return redirect("surveys:home")
    questions = template_questions(campaign.template, section=scope)
    if request.method == "POST":
        cleaned, errors, values = validate_answers(questions, request.POST)
        if errors:
            context = _form_context(campaign, target, questions, targets, values, errors)
            return render(request, "surveys/form.html", context, status=400)
        try:
            submit_target(campaign=campaign, student=request.user, target=target, cleaned_answers=cleaned)
        except AlreadySubmitted as exc:
            messages.info(request, exc.messages[0])
            return redirect("surveys:home")
        except SubmissionClosed as exc:
            messages.warning(request, exc.messages[0])
            return redirect("surveys:home")
        refreshed = student_targets(campaign, request.user)
        _remember(request, organization, campaign, refreshed)
        upcoming = next_pending(refreshed)
        if upcoming is None:
            return redirect("surveys:thanks")
        messages.success(request, pgettext(_CTX, "Cavabınız anonim şəkildə qeydə alındı."))
        return redirect(_target_url(campaign, upcoming))
    return render(request, "surveys/form.html", _form_context(campaign, target, questions, targets))


def _target_url(campaign, target):
    if target.is_general:
        return reverse("surveys:general", args=[campaign.pk])
    return reverse("surveys:teacher", args=[campaign.pk, target.offering_id, target.teacher_id])


@login_required
@require_http_methods(["GET", "POST"])
def teacher_form(request, campaign_id, offering_id, teacher_id):
    organization, denied = _guard(request)
    if denied:
        return denied
    campaign = _campaign_or_none(organization, campaign_id)
    if campaign is None:
        messages.info(request, pgettext(_CTX, "Bu sorğu hazırda qəbul edilmir."))
        return redirect("surveys:home")
    return _handle_form(
        request, organization, campaign, scope=Section.TEACHER, offering_id=offering_id, teacher_id=teacher_id
    )


@login_required
@require_http_methods(["GET", "POST"])
def general_form(request, campaign_id):
    organization, denied = _guard(request)
    if denied:
        return denied
    campaign = _campaign_or_none(organization, campaign_id)
    if campaign is None:
        messages.info(request, pgettext(_CTX, "Bu sorğu hazırda qəbul edilmir."))
        return redirect("surveys:home")
    return _handle_form(request, organization, campaign, scope=Section.GENERAL)


@login_required
def thanks(request):
    organization, denied = _guard(request)
    if denied:
        return denied
    return render(request, "surveys/thanks.html", {"cabinet_url": reverse("accounts:profile")})


@login_required
@require_POST
def defer(request):
    """«Sonra doldur» — yalnız ``grace_until``-a qədər, 24 saatlıq möhlət."""
    organization, denied = _guard(request)
    if denied:
        return denied
    campaign = _campaign_or_none(organization, request.POST.get("campaign") or None)
    if campaign is None or not campaign.grace_applies_on(timezone.localdate()):
        messages.warning(request, pgettext(_CTX, "Möhlət müddəti bitib — sorğunu doldurmaq məcburidir."))
        return redirect("surveys:home")
    set_deferral(request, campaign.pk)
    messages.info(request, pgettext(_CTX, "Sorğunu 24 saat ərzində doldurmağı unutmayın."))
    return redirect("accounts:profile")
