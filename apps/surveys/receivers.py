"""Registrar hadisələrinə abunə — «jurnal bağlandı → dövrün sorğusu açılsın».

``registrar.journal_close.close_journals`` HƏQİQƏTƏN jurnal bağlayanda
``journal_closed`` siqnalını commit-dən SONRA göndərir. Burada dövrün kampaniyası
idempotent yaradılır/açılır (``Organization.settings["surveys"]["auto_open"]``
söndürülübsə — heç nə), qapı xülasəsinin versiyası yenilənir (yeni hədəflər) və
YENİ uyğun tələbələrə bildiriş gedir. Xəta bağlama əməlini POZMUR (loglanır).

MODUL SƏRHƏDİ: siqnal registrar-ın public səthindən (``apps.registrar.public``
→ ``journal_close`` servisi) götürülür; ``apps.registrar.signals`` birbaşa
import edilmir (``scripts/public_api_boundaries.py``).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from apps.registrar.public import journal_close as registrar_journal_close
from core.rls import set_rls_tenant
from core.rls_pooling import rls_worker_atomic

from .constants import CampaignStatus, OpenedVia

logger = logging.getLogger(__name__)


def handle_journals_closed(organization, period, offering_ids, *, by_user=None) -> dict:
    """Siqnalın işi (əmr və testlər də çağırır). Qaytarır: qısa hesabat dict-i."""
    from .models import SurveyCampaign
    from .services import notify
    from .services.campaigns import ensure_campaign
    from .services.config import survey_config
    from .services.gate_snapshot import sync_gate_snapshot

    report = {"campaign": None, "created": False, "opened": False, "notified": 0}
    if organization is None or period is None or not survey_config(organization).auto_open:
        return report
    existing = SurveyCampaign.objects.filter(organization=organization, period=period).first()
    if existing is not None and existing.status == CampaignStatus.CLOSED:
        # Kimsə qəsdən bağlayıb — avtomatik yenidən açılmır.
        report["campaign"] = existing
        return report
    if existing is None or existing.status == CampaignStatus.DRAFT:
        campaign, created, opened = ensure_campaign(
            organization, period, by_user=by_user, via=OpenedVia.JOURNAL_CLOSE, open_now=True
        )
    else:
        campaign, created, opened = existing, False, False
        sync_gate_snapshot(organization)  # yeni hədəflər → sessiya sayğacları təzələnsin
    report.update(campaign=campaign, created=created, opened=opened)
    if not campaign.is_active_on(timezone.localdate()):
        return report
    if opened:
        students = notify.eligible_student_ids(organization, period.pk)
    else:
        students = notify.newly_eligible_students(organization, period.pk, offering_ids)
    notify.notify_campaign_opened(organization, campaign, students)
    report["notified"] = len(students)
    return report


@receiver(registrar_journal_close.journal_closed, dispatch_uid="surveys.receivers.journal_closed")
def _on_journal_closed(sender, organization=None, period=None, offering_ids=None, by_user=None, **kwargs):
    try:
        with transaction.atomic(), rls_worker_atomic():
            if organization is not None:
                set_rls_tenant(organization.pk)
            handle_journals_closed(organization, period, offering_ids or [], by_user=by_user)
    except Exception:  # noqa: BLE001 — sorğu kampaniyası jurnal bağlamasını bloklamamalıdır
        logger.exception("survey auto-open after journal close failed (period=%s)", getattr(period, "pk", None))
