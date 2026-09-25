"""Kampaniyanın həyat dövrü — yaratmaq/açmaq/bağlamaq/uzatmaq (atomik, auditli).

Hər dəyişiklik eyni tranzaksiyada qapı xülasəsini (``gate_snapshot``) yeniləyir
və audit jurnalına yazılır. Kampaniya dövr başına BİRDİR (``(org, period)``
unikal); ``ensure_campaign`` bunu idempotent edir (paralel çağırış → mövcud sətir).
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import (
    AUDIT_RESOURCE_TYPE,
    MAX_CAMPAIGN_DAYS,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    CampaignStatus,
    OpenedVia,
)
from ..models import SurveyCampaign
from .config import survey_config
from .gate_snapshot import sync_gate_snapshot
from .templates import default_template_for

_CTX = "surveys.campaigns"


class CampaignError(ValidationError):
    """İstifadəçiyə göstərilə bilən kampaniya xətası."""


def _audit(campaign, *, by_user, action, changes, request=None):
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.UPDATE if action != "create" else AuditAction.CREATE,
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=campaign.organization,
        obj=None,
        reason=f"survey_campaign_{action}",
        request=request,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(campaign.pk),
        resource_repr=f"{action} · {getattr(campaign.period, 'name', '—')}",
        changes={"action": action, **{key: str(value) for key, value in changes.items()}},
    )


def _validate(opens_on, closes_on, grace_until, min_group_size):
    if min_group_size is not None and not (MIN_GROUP_SIZE_FLOOR <= int(min_group_size) <= MIN_GROUP_SIZE_CEIL):
        raise CampaignError(
            pgettext(_CTX, "Minimum qrup ölçüsü %(low)s ilə %(high)s arasında olmalıdır.")
            % {"low": MIN_GROUP_SIZE_FLOOR, "high": MIN_GROUP_SIZE_CEIL}
        )
    if opens_on and closes_on:
        if closes_on < opens_on:
            raise CampaignError(pgettext(_CTX, "Bağlanma tarixi açılış tarixindən əvvəl ola bilməz."))
        if (closes_on - opens_on).days > MAX_CAMPAIGN_DAYS:
            raise CampaignError(
                pgettext(_CTX, "Kampaniya %(days)s gündən uzun ola bilməz.") % {"days": MAX_CAMPAIGN_DAYS}
            )
    if grace_until and opens_on and grace_until < opens_on:
        raise CampaignError(pgettext(_CTX, "«Sonra doldur» müddəti açılış tarixindən əvvəl bitə bilməz."))
    if grace_until and closes_on and grace_until > closes_on:
        raise CampaignError(pgettext(_CTX, "«Sonra doldur» müddəti bağlanma tarixindən sonra ola bilməz."))


def _open_fields(campaign, organization, *, today, via):
    config = survey_config(organization)
    campaign.status = CampaignStatus.OPEN
    campaign.opens_on = campaign.opens_on if campaign.opens_on and campaign.opens_on >= today else today
    closes_on = campaign.closes_on
    if not closes_on or closes_on < campaign.opens_on:
        closes_on = campaign.opens_on + datetime.timedelta(days=config.close_after_days)
    campaign.closes_on = closes_on
    if campaign.grace_until is None or campaign.grace_until < campaign.opens_on:
        grace = campaign.opens_on + datetime.timedelta(days=config.grace_days) if config.grace_days else None
        campaign.grace_until = min(grace, closes_on) if grace else None
    campaign.opened_via = via
    campaign.opened_at = timezone.now()
    campaign.closed_at = None


def ensure_campaign(organization, period, *, by_user=None, via=OpenedVia.MANUAL, open_now=True, request=None):
    """Dövrün kampaniyasını yaradır/açır. Qaytarır: ``(campaign, created, opened)``.

    Bağlı (``closed``) kampaniya AVTOMATİK yenidən açılmır — onu kimsə qəsdən
    bağlayıb; yenidən açılış yalnız :func:`reopen_campaign` ilə (əl ilə) olur.
    """
    today = timezone.localdate()
    config = survey_config(organization)
    with transaction.atomic():
        campaign = SurveyCampaign.objects.select_for_update().filter(organization=organization, period=period).first()
        created = False
        if campaign is None:
            try:
                with transaction.atomic():
                    campaign = SurveyCampaign.objects.create(
                        organization=organization,
                        period=period,
                        template=default_template_for(organization),
                        status=CampaignStatus.DRAFT,
                        mandatory=config.mandatory,
                        min_group_size=config.min_group_size,
                        opened_via=via,
                        created_by=by_user if getattr(by_user, "pk", None) else None,
                    )
                created = True
            except IntegrityError:
                campaign = SurveyCampaign.objects.select_for_update().get(organization=organization, period=period)
        opened = False
        if open_now and campaign.status == CampaignStatus.DRAFT:
            _open_fields(campaign, organization, today=today, via=via)
            campaign.save()
            opened = True
        if created or opened:
            _audit(
                campaign,
                by_user=by_user,
                action="open" if opened else "create",
                changes={"via": via, "closes_on": campaign.closes_on, "grace_until": campaign.grace_until},
                request=request,
            )
        sync_gate_snapshot(organization)
    return campaign, created, opened


def _locked(campaign):
    return SurveyCampaign.objects.select_for_update().select_related("period", "organization").get(pk=campaign.pk)


def open_campaign(campaign, *, by_user, request=None):
    with transaction.atomic():
        campaign = _locked(campaign)
        if campaign.status != CampaignStatus.DRAFT:
            raise CampaignError(pgettext(_CTX, "Yalnız qaralama kampaniyası açıla bilər."))
        _open_fields(campaign, campaign.organization, today=timezone.localdate(), via=OpenedVia.MANUAL)
        campaign.save()
        _audit(campaign, by_user=by_user, action="open", changes={"closes_on": campaign.closes_on}, request=request)
        sync_gate_snapshot(campaign.organization)
    return campaign


def close_campaign(campaign, *, by_user, request=None):
    with transaction.atomic():
        campaign = _locked(campaign)
        if campaign.status == CampaignStatus.CLOSED:
            return campaign
        campaign.status = CampaignStatus.CLOSED
        campaign.closed_at = timezone.now()
        campaign.save(update_fields=["status", "closed_at", "updated_at"])
        _audit(campaign, by_user=by_user, action="close", changes={}, request=request)
        sync_gate_snapshot(campaign.organization)
    return campaign


def reopen_campaign(campaign, *, by_user, closes_on=None, request=None):
    today = timezone.localdate()
    with transaction.atomic():
        campaign = _locked(campaign)
        if campaign.status != CampaignStatus.CLOSED:
            raise CampaignError(pgettext(_CTX, "Yalnız bağlı kampaniya yenidən açıla bilər."))
        target_close = closes_on or campaign.closes_on
        if not target_close or target_close < today:
            raise CampaignError(pgettext(_CTX, "Yenidən açmaq üçün gələcək bağlanma tarixi seçin."))
        _validate(campaign.opens_on, target_close, campaign.grace_until, campaign.min_group_size)
        campaign.status = CampaignStatus.OPEN
        campaign.closes_on = target_close
        campaign.closed_at = None
        campaign.save(update_fields=["status", "closes_on", "closed_at", "updated_at"])
        _audit(campaign, by_user=by_user, action="reopen", changes={"closes_on": target_close}, request=request)
        sync_gate_snapshot(campaign.organization)
    return campaign


_UNSET = object()


def update_campaign(
    campaign,
    *,
    by_user,
    closes_on=_UNSET,
    grace_until=_UNSET,
    min_group_size=_UNSET,
    mandatory=_UNSET,
    request=None,
):
    """Tarixlər / k-həddi / məcburilik — yalnız ötürülən sahələr dəyişir."""
    with transaction.atomic():
        campaign = _locked(campaign)
        new_values = {
            "closes_on": campaign.closes_on if closes_on is _UNSET else closes_on,
            "grace_until": campaign.grace_until if grace_until is _UNSET else grace_until,
            "min_group_size": campaign.min_group_size if min_group_size is _UNSET else int(min_group_size),
            "mandatory": campaign.mandatory if mandatory is _UNSET else bool(mandatory),
        }
        _validate(campaign.opens_on, new_values["closes_on"], new_values["grace_until"], new_values["min_group_size"])
        changes = {key: value for key, value in new_values.items() if getattr(campaign, key) != value}
        if not changes:
            return campaign
        for key, value in changes.items():
            setattr(campaign, key, value)
        campaign.save(update_fields=[*changes, "updated_at"])
        _audit(campaign, by_user=by_user, action="update", changes=changes, request=request)
        sync_gate_snapshot(campaign.organization)
    return campaign
