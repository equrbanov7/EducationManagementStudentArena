"""Sistem Monitorinqi API-ları — hamısı superadmin-only (permissions.py).

Frontend yalnız bu endpoint-lərə müraciət edir; Prometheus/Loki/Alertmanager
heç vaxt birbaşa açılmır. Asılılıq əlçatmazdırsa cavab ``status="degraded"``
olur — UI boz vəziyyət göstərir, imtahan sisteminə təsir yoxdur.
"""

from __future__ import annotations

import hmac
import json
import logging
import time

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import queries
from .clients import AlertmanagerClient, LokiClient, PrometheusClient, degraded
from .models import Incident, IncidentStatus, SecurityEvent
from .permissions import superadmin_monitoring_required

logger = logging.getLogger(__name__)

PAGE_SIZE = 25


def _range_seconds(request) -> int:
    try:
        return int(request.GET.get("range", 3600))
    except (TypeError, ValueError):
        return 3600


@require_GET
@superadmin_monitoring_required
def overview_api(request):
    prom = PrometheusClient()
    targets = prom.query("up")
    if targets is None:
        return JsonResponse(degraded("prometheus", "Metrik servisi müvəqqəti əlçatmazdır"))

    up_by_job: dict[str, bool] = {}
    for item in targets:
        job = item.get("metric", {}).get("job", "?")
        try:
            value = float(item["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            value = 0.0
        up_by_job[job] = up_by_job.get(job, True) and value == 1.0

    containers_alive = prom.scalar(f"count(time() - container_last_seen{{{queries.CONTAINER_RE}}} < 60)", 0.0)
    data = {
        "generated_at": timezone.now().isoformat(),
        "targets": up_by_job,
        "server": {
            "cpu_percent": prom.scalar('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'),
            "memory_percent": prom.scalar("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"),
            "disk_percent": prom.scalar(
                '100 * (1 - node_filesystem_avail_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"}'
                ' / node_filesystem_size_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"})'
            ),
            "uptime_seconds": prom.scalar("node_time_seconds - node_boot_time_seconds"),
        },
        "containers_alive": containers_alive,
        "app": {
            "request_rate": prom.scalar("sum(rate(http_requests_total[5m]))"),
            "error_rate_percent": prom.scalar(
                'sum(rate(http_requests_total{status_code=~"5.."}[5m]))'
                " / clamp_min(sum(rate(http_requests_total[5m])), 0.001) * 100"
            ),
            "p95_seconds": prom.scalar(
                "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[15m])))"
            ),
        },
        "services": {
            "postgres_up": prom.scalar("pg_up"),
            "redis_up": prom.scalar("redis_up"),
            "nginx_up": prom.scalar("nginx_up"),
            "celery_workers": prom.scalar("emsarena_celery_workers_online"),
            "backup_age_seconds": prom.scalar("emsarena_backup_age_seconds"),
        },
        "incidents_open": Incident.objects.exclude(status=IncidentStatus.RESOLVED).count(),
        "incidents_critical_open": Incident.objects.filter(severity="critical")
        .exclude(status=IncidentStatus.RESOLVED)
        .count(),
        "security_events_24h": SecurityEvent.objects.filter(
            last_seen_at__gte=timezone.now() - timezone.timedelta(hours=24)
        ).count(),
    }
    from apps.exams.models import Exam, ExamAttempt

    now = timezone.now()
    data["exams"] = {
        "active_exams": Exam.objects.filter(is_deleted=False, start_datetime__lte=now, end_datetime__gte=now).count(),
        "students_in_exam": ExamAttempt.objects.filter(status="in_progress").count(),
    }
    return JsonResponse({"status": "ok", "data": data})


@require_GET
@superadmin_monitoring_required
def server_api(request):
    return JsonResponse(queries.server_section(_range_seconds(request)))


@require_GET
@superadmin_monitoring_required
def containers_api(request):
    return JsonResponse(queries.containers_section())


@require_GET
@superadmin_monitoring_required
def application_api(request):
    return JsonResponse(queries.application_section(_range_seconds(request)))


@require_GET
@superadmin_monitoring_required
def database_api(request):
    return JsonResponse(queries.database_section(_range_seconds(request)))


@require_GET
@superadmin_monitoring_required
def redis_celery_api(request):
    return JsonResponse(queries.redis_celery_section(_range_seconds(request)))


@require_GET
@superadmin_monitoring_required
def exams_api(request):
    return JsonResponse(queries.exams_section(_range_seconds(request)))


@require_GET
@superadmin_monitoring_required
def alerts_api(request):
    client = AlertmanagerClient()
    alerts = client.alerts()
    if alerts is None:
        return JsonResponse(degraded("alertmanager", "Alertmanager müvəqqəti əlçatmazdır"))
    rows = []
    for alert in alerts[:100]:
        labels = alert.get("labels", {}) or {}
        rows.append(
            {
                "name": labels.get("alertname", "?"),
                "severity": labels.get("severity", ""),
                "state": (alert.get("status") or {}).get("state", ""),
                "silenced": bool((alert.get("status") or {}).get("silencedBy")),
                "starts_at": alert.get("startsAt", ""),
                "summary": (alert.get("annotations") or {}).get("summary", ""),
            }
        )
    return JsonResponse({"status": "ok", "data": {"alerts": rows}})


@require_GET
@superadmin_monitoring_required
def logs_api(request):
    """Loki log axtarışı: servis + severity + mətn filtri, sərt limitlərlə."""
    container = (request.GET.get("container") or "").strip()[:80]
    search = (request.GET.get("q") or "").strip()[:120]
    level = (request.GET.get("level") or "").strip().lower()
    range_seconds, _ = queries.clamp_range(_range_seconds(request))

    selector = f'{{container=~"{container}.*"}}' if container else '{job="docker"}'
    logql = selector
    if search:
        escaped = search.replace("\\", "\\\\").replace("`", "")
        logql += f" |= `{escaped}`"
    if level in {"error", "warning", "critical"}:
        logql += f" |~ `(?i){level}`"

    end_ns = time.time_ns()
    start_ns = end_ns - range_seconds * 1_000_000_000
    client = LokiClient()
    result = client.query_range(logql, start_ns=start_ns, end_ns=end_ns, limit=200)
    if result is None:
        return JsonResponse(degraded("loki", "Log servisi müvəqqəti əlçatmazdır"))

    lines = []
    for stream in result:
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            lines.append(
                {
                    "ts": int(ts) // 1_000_000,  # ms
                    "container": labels.get("container", ""),
                    "line": line[:1000],
                }
            )
    lines.sort(key=lambda row: row["ts"], reverse=True)
    containers = client.labels_values("container") or []
    return JsonResponse({"status": "ok", "data": {"lines": lines[:200], "containers": containers}})


@require_GET
@superadmin_monitoring_required
def incidents_api(request):
    status_filter = request.GET.get("status", "")
    qs = Incident.objects.all()
    if status_filter == "open":
        qs = qs.exclude(status=IncidentStatus.RESOLVED)
    elif status_filter:
        qs = qs.filter(status=status_filter)
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    total = qs.count()
    rows = [
        {
            "id": incident.pk,
            "title": incident.title,
            "severity": incident.severity,
            "status": incident.status,
            "service": incident.service,
            "alert_rule": incident.alert_rule,
            "started_at": incident.started_at.isoformat() if incident.started_at else None,
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "duration_seconds": incident.duration_seconds,
            "assigned_to": getattr(incident.assigned_to, "username", None),
            "resolution_note": incident.resolution_note,
        }
        for incident in qs.select_related("assigned_to")[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    ]
    return JsonResponse({"status": "ok", "data": {"incidents": rows, "total": total, "page": page}})


@require_POST
@superadmin_monitoring_required
def incident_action_api(request, incident_id: int):
    from .incidents import apply_incident_action

    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        return JsonResponse({"detail": "İnsident tapılmadı."}, status=404)
    action = request.POST.get("action", "")
    note = (request.POST.get("note") or "").strip()[:2000]
    if not apply_incident_action(incident, action=action, user=request.user, note=note):
        return JsonResponse({"detail": "Yanlış əməliyyat."}, status=400)
    return JsonResponse({"status": "ok", "data": {"id": incident.pk, "new_status": incident.status}})


@require_GET
@superadmin_monitoring_required
def security_events_api(request):
    qs = SecurityEvent.objects.select_related("user", "incident")
    event_type = request.GET.get("type", "")
    if event_type:
        qs = qs.filter(event_type=event_type)
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    total = qs.count()
    rows = [
        {
            "id": event.pk,
            "event_type": event.event_type,
            "event_type_display": event.get_event_type_display(),
            "severity": event.severity,
            "user": getattr(event.user, "username", None) or event.username_hint or None,
            "ip": event.ip_address,
            "message": event.message,
            "count": event.count,
            "first_seen": event.created_at.isoformat(),
            "last_seen": event.last_seen_at.isoformat(),
            "resolved": event.resolved,
        }
        for event in qs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    ]
    return JsonResponse({"status": "ok", "data": {"events": rows, "total": total, "page": page}})


@csrf_exempt
@require_POST
def alertmanager_webhook(request):
    """Alertmanager → insident axını. Token ilə qorunur, yalnız daxili şəbəkə.

    CSRF-exempt-dir çünki maşın-maşın sorğusudur; giriş nəzarəti paylaşılan
    token-lədir (ALERTMANAGER_WEBHOOK_TOKEN) və nginx bu path-i publik marşruta
    çıxarmır (app konteynerinə yalnız daxili şəbəkədən çatmaq olar).
    """
    expected = getattr(settings, "ALERTMANAGER_WEBHOOK_TOKEN", "") or ""
    provided = request.GET.get("token", "")
    if not expected or not hmac.compare_digest(expected, provided):
        logger.warning("Alertmanager webhook: yanlış token (uzaq=%s)", request.META.get("REMOTE_ADDR"))
        return HttpResponseForbidden("forbidden")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"detail": "invalid payload"}, status=400)

    from .incidents import ingest_alertmanager_payload

    result = ingest_alertmanager_payload(payload)
    return JsonResponse({"status": "ok", **result})
