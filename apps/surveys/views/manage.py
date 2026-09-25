"""«Sorğu kampaniyaları» bölməsinin POST ucu — ``/sorgu/idare/`` (``survey.manage``).

Bölmənin özü kabinetdə render olunur (``accounts/profile/sections/_evaluation_campaigns.html``
→ ``survey_cabinet`` template tag-ı); bu ucu yalnız əməlləri icra edib ``next``-ə
(eyni host) qayıdır. İcazə burada FAIL-CLOSED yenidən yoxlanılır: org-wide
``survey.manage`` və ya superadmin. View-as READONLY yazıları middleware bloklayır.
"""

from __future__ import annotations

import datetime
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from ..models import SurveyCampaign
from ..services import campaigns as campaign_service
from ..services.access import can_manage_campaigns

_CTX = "surveys.manage"


def _section_url():
    return reverse("accounts:profile") + "?section=evaluation-campaigns"


def _next_url(request):
    candidate = (request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return _section_url()


def _date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(pgettext(_CTX, "Tarix düzgün formatda deyil.")) from exc


def _campaign(organization, raw_id):
    try:
        pk = uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(pgettext(_CTX, "Kampaniya tapılmadı.")) from exc
    campaign = SurveyCampaign.objects.filter(organization=organization, pk=pk).select_related("period").first()
    if campaign is None:
        raise ValidationError(pgettext(_CTX, "Kampaniya tapılmadı."))
    return campaign


def _period(organization, raw_id):
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    try:
        pk = uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(pgettext(_CTX, "Semestr seçilməlidir.")) from exc
    period = AcademicPeriod.objects.filter(organization=organization, pk=pk).first()
    if period is None:
        raise ValidationError(pgettext(_CTX, "Semestr seçilməlidir."))
    return period


def _dispatch(request, organization, action):
    post = request.POST
    user = request.user
    if action == "create_open":
        campaign, created, opened = campaign_service.ensure_campaign(
            organization, _period(organization, post.get("period")), by_user=user, request=request
        )
        if not opened and campaign.status != "open":
            raise ValidationError(pgettext(_CTX, "Bu semestrin kampaniyası artıq var — onu cədvəldən idarə edin."))
        return pgettext(_CTX, "Kampaniya açıldı.")
    campaign = _campaign(organization, post.get("campaign"))
    if action == "open":
        campaign_service.open_campaign(campaign, by_user=user, request=request)
        return pgettext(_CTX, "Kampaniya açıldı.")
    if action == "close":
        campaign_service.close_campaign(campaign, by_user=user, request=request)
        return pgettext(_CTX, "Kampaniya bağlandı.")
    if action == "reopen":
        campaign_service.reopen_campaign(
            campaign, by_user=user, closes_on=_date(post.get("closes_on")), request=request
        )
        return pgettext(_CTX, "Kampaniya yenidən açıldı.")
    if action == "update":
        try:
            min_group_size = int(post.get("min_group_size") or campaign.min_group_size)
        except ValueError as exc:
            raise ValidationError(pgettext(_CTX, "Minimum qrup ölçüsü tam ədəd olmalıdır.")) from exc
        campaign_service.update_campaign(
            campaign,
            by_user=user,
            closes_on=_date(post.get("closes_on")) or campaign.closes_on,
            grace_until=_date(post.get("grace_until")),
            min_group_size=min_group_size,
            mandatory=post.get("mandatory") == "1",
            request=request,
        )
        return pgettext(_CTX, "Kampaniya yeniləndi.")
    raise ValidationError(pgettext(_CTX, "Naməlum əməliyyat."))


@login_required
@require_POST
def manage(request):
    organization = getattr(request, "organization", None)
    if not can_manage_campaigns(request.user, organization, request=request):
        return HttpResponseForbidden(pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."))
    next_url = _next_url(request)
    try:
        messages.success(request, _dispatch(request, organization, (request.POST.get("action") or "").strip()))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(next_url)
