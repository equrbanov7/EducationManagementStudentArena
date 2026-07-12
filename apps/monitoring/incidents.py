"""İnsident idarəetməsi: Alertmanager webhook → Incident + bildirişlər.

Axın: Prometheus alert → Alertmanager (dedup/qruplaşdırma/cooldown orada) →
webhook → burada fingerprint üzrə insident yaranır/həll olunur → bütün
superadminlərə in-app bildiriş (e-poçt Alertmanager-in öz receiver-i ilə
gedir). Resolve gələndə bərpa bildirişi + müddət yazılır. Hər status
dəyişikliyi audit log-a düşür.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Incident, IncidentStatus

logger = logging.getLogger(__name__)

#: Alertmanager severity → daxili severity xəritəsi.
_SEVERITY_MAP = {"critical": "critical", "warning": "medium", "info": "info"}


def _superadmins():
    User = get_user_model()
    users = list(User.objects.filter(is_superuser=True, is_active=True))
    # Platforma is_superadmin bayrağı ayrıca sahə kimi varsa onu da əhatə et.
    try:
        extra = User.objects.filter(is_active=True, is_superadmin=True)
        seen = {u.pk for u in users}
        users.extend(u for u in extra if u.pk not in seen)
    except Exception:  # pragma: no cover - sahə yoxdursa
        pass
    return users


def _monitoring_link() -> str:
    try:
        return reverse("accounts:profile") + "?section=system-monitoring"
    except Exception:  # pragma: no cover
        return "/accounts/profile/?section=system-monitoring"


def _notify(incident: Incident, *, resolved: bool):
    from apps.notifications.services.crud import create_notification

    if resolved:
        minutes, seconds = divmod(incident.duration_seconds or 0, 60)
        title = f"HƏLL OLUNDU: {incident.title}"
        message = (
            f"İnsident müddəti: {minutes} dəq {seconds} san.\n"
            f"Servis: {incident.service or '-'} · Mühit: {incident.environment}"
        )
    else:
        title = f"{incident.get_severity_display().upper()}: {incident.title}"
        description = incident.annotations.get("description", "") or incident.description
        message = f"Servis: {incident.service or '-'} · Mühit: {incident.environment}\n" f"{description}".strip()

    delivered = 0
    for admin in _superadmins():
        try:
            create_notification(
                recipient=admin,
                title=title[:255],
                message=message,
                link=_monitoring_link(),
                notification_type="system",
                metadata={"incident_id": incident.pk, "severity": incident.severity},
                organization=None,
            )
            delivered += 1
        except Exception:  # pragma: no cover
            logger.exception("Monitorinq bildirişi göndərilmədi (user=%s)", admin.pk)
    incident.add_delivery("in_app", delivered > 0, f"{delivered} superadmin")
    incident.save(update_fields=["delivery_log"])


def _audit_incident(incident: Incident, action_note: str, user=None):
    try:
        from core.audit import log_action

        log_action(
            "update",
            user=user,
            obj=incident,
            resource_type="monitoring.incident",
            resource_id=str(incident.pk),
            resource_repr=incident.title[:500],
            reason=action_note,
        )
    except Exception:  # pragma: no cover
        logger.exception("İnsident audit yazısı alınmadı")


def ingest_alertmanager_payload(payload: dict) -> dict:
    """Webhook gövdəsini emal et; {"created": n, "resolved": n} qaytar."""
    created = 0
    resolved = 0
    for alert in (payload or {}).get("alerts", [])[:50]:
        labels = alert.get("labels", {}) or {}
        annotations = alert.get("annotations", {}) or {}
        fingerprint = alert.get("fingerprint") or f"{labels.get('alertname', '?')}:{labels.get('instance', '')}"
        status = alert.get("status", "firing")

        if status == "resolved":
            incident = (
                Incident.objects.filter(fingerprint=fingerprint)
                .exclude(status__in=[IncidentStatus.RESOLVED])
                .order_by("-started_at")
                .first()
            )
            if incident is None:
                continue
            incident.status = IncidentStatus.RESOLVED
            incident.resolved_at = parse_datetime(alert.get("endsAt") or "") or timezone.now()
            incident.save(update_fields=["status", "resolved_at"])
            _audit_incident(incident, "Alertmanager resolved siqnalı ilə avtomatik həll")
            _notify(incident, resolved=True)
            resolved += 1
            continue

        # firing: eyni fingerprint-li açıq insident varsa təkrar yaratma
        # (Alertmanager repeat_interval xatırlatmaları burada dublikat olmur).
        existing = Incident.objects.filter(fingerprint=fingerprint).exclude(status=IncidentStatus.RESOLVED).first()
        if existing is not None:
            continue

        incident = Incident.objects.create(
            title=annotations.get("summary") or labels.get("alertname", "Naməlum alert"),
            description=annotations.get("description", ""),
            severity=_SEVERITY_MAP.get(labels.get("severity", ""), "medium"),
            source="alertmanager",
            service=labels.get("job", "") or labels.get("service", ""),
            alert_rule=labels.get("alertname", ""),
            fingerprint=fingerprint,
            started_at=parse_datetime(alert.get("startsAt") or "") or timezone.now(),
            labels={k: str(v)[:200] for k, v in list(labels.items())[:20]},
            annotations={k: str(v)[:500] for k, v in list(annotations.items())[:10]},
        )
        _audit_incident(incident, "Alertmanager firing siqnalı ilə yaradıldı")
        _notify(incident, resolved=False)
        created += 1

    return {"created": created, "resolved": resolved}


def apply_incident_action(incident: Incident, *, action: str, user, note: str = "") -> bool:
    """UI əməliyyatları: acknowledge / investigating / monitoring / resolve / silence."""
    now = timezone.now()
    if action == "acknowledge":
        incident.status = IncidentStatus.ACKNOWLEDGED
        incident.acknowledged_at = now
        incident.acknowledged_by = user
        if incident.assigned_to_id is None:
            incident.assigned_to = user
    elif action == "investigating":
        incident.status = IncidentStatus.INVESTIGATING
        incident.assigned_to = incident.assigned_to or user
    elif action == "monitoring":
        incident.status = IncidentStatus.MONITORING
    elif action == "resolve":
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = now
        incident.resolved_by = user
        if note:
            incident.resolution_note = note
    elif action == "silence":
        incident.status = IncidentStatus.SILENCED
    else:
        return False

    if note and action != "resolve":
        incident.resolution_note = (incident.resolution_note + "\n" if incident.resolution_note else "") + note
    incident.save()
    _audit_incident(incident, f"Status dəyişikliyi: {action}", user=user)
    if action == "resolve":
        _notify(incident, resolved=True)
    return True
