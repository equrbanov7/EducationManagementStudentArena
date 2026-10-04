"""Sistem Monitorinqi API-ları (permissions.py).

OXU endpoint-ləri ``monitoring_view_required`` ilə qapılıdır: superadmin VƏ YA
``system.monitoring.view`` icazəli üzv (RİM rəhbəri, 2026-10-01). İcazəli üzv
tenant sətirlərində (təhlükəsizlik hadisələri, imtahan sayları) yalnız ÖZ
təşkilatını + org-suz sətirləri görür; insident ƏMƏLLƏRİ superadmin-only qalır.
Log sətirləri UI-a getməzdən əvvəl ``scrub.redact_secrets``-dən keçir.

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
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import queries
from .clients import LOKI_MAX_LINES, AlertmanagerClient, LokiClient, PrometheusClient, degraded
from .models import Incident, IncidentStatus, SecurityEvent
from .pagination import clamp_page, paginated_data, parse_pagination
from .permissions import monitoring_view_required, superadmin_monitoring_required
from .scrub import redact_secrets
from .security_ip import InvalidIpFilter, parse_ip_filter, successful_logins

logger = logging.getLogger(__name__)


def _scope(request):
    return getattr(request, "monitoring_scope", None)


def _org_filter(request, field: str = "organization_id") -> Q:
    """İcazəli üzv üçün: öz təşkilatı + org-suz sətirlər; superadmin üçün filtr yoxdur."""
    scope = _scope(request)
    if scope is None or scope.platform:
        return Q()
    return Q(**{f"{field}__isnull": True}) | Q(**{field: scope.organization_id})


def _range_seconds(request) -> int:
    try:
        return int(request.GET.get("range", 3600))
    except (TypeError, ValueError):
        return 3600


@require_GET
@monitoring_view_required
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
            "disk_percent": prom.scalar(queries.ROOT_DISK_USED_PERCENT_PROMQL),
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
            "endpoint_probes_up": prom.scalar('min(probe_success{job="emsarena-blackbox"})'),
            "celery_workers": prom.scalar("emsarena_celery_workers_online"),
            "backup_age_seconds": prom.scalar("emsarena_backup_age_seconds"),
        },
        "incidents_open": Incident.objects.exclude(status=IncidentStatus.RESOLVED).count(),
        "incidents_critical_open": Incident.objects.filter(severity="critical")
        .exclude(status=IncidentStatus.RESOLVED)
        .count(),
    }
    from apps.exams.models import Exam, ExamAttempt

    now = timezone.now()
    scope = _scope(request)
    exam_q = Q() if scope is None or scope.platform else Q(organization_id=scope.organization_id)
    attempt_q = Q() if scope is None or scope.platform else Q(exam__organization_id=scope.organization_id)
    data["security_events_24h"] = SecurityEvent.objects.filter(
        _org_filter(request), last_seen_at__gte=now - timezone.timedelta(hours=24)
    ).count()
    data["exams"] = {
        "active_exams": Exam.objects.filter(
            exam_q, is_deleted=False, start_datetime__lte=now, end_datetime__gte=now
        ).count(),
        "students_in_exam": ExamAttempt.objects.filter(attempt_q, status="in_progress").count(),
    }
    return JsonResponse({"status": "ok", "data": data})


@require_GET
@monitoring_view_required
def server_api(request):
    return JsonResponse(queries.server_section(_range_seconds(request)))


@require_GET
@monitoring_view_required
def containers_api(request):
    page, page_size = parse_pagination(request.GET)
    return JsonResponse(queries.containers_section(page=page, page_size=page_size))


@require_GET
@monitoring_view_required
def application_api(request):
    return JsonResponse(queries.application_section(_range_seconds(request)))


@require_GET
@monitoring_view_required
def database_api(request):
    return JsonResponse(queries.database_section(_range_seconds(request)))


@require_GET
@monitoring_view_required
def redis_celery_api(request):
    return JsonResponse(queries.redis_celery_section(_range_seconds(request)))


@require_GET
@monitoring_view_required
def exams_api(request):
    scope = _scope(request)
    organization_id = None if scope is None or scope.platform else scope.organization_id
    return JsonResponse(queries.exams_section(_range_seconds(request), organization_id=organization_id))


@require_GET
@monitoring_view_required
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
                "summary": redact_secrets((alert.get("annotations") or {}).get("summary", "")),
            }
        )
    return JsonResponse({"status": "ok", "data": {"alerts": rows}})


@require_GET
@monitoring_view_required
def logs_api(request):
    """Loki log axtarışı: servis + severity + mətn filtri, sərt limitlərlə."""
    container = (request.GET.get("container") or "").strip()[:80]
    search = (request.GET.get("q") or "").strip()[:120]
    level = (request.GET.get("level") or "").strip().lower()
    range_seconds, _ = queries.clamp_range(_range_seconds(request))

    selector = f"{{container={json.dumps(container, ensure_ascii=False)}}}" if container else '{job="docker"}'
    logql = selector
    if search:
        escaped = search.replace("\\", "\\\\").replace("`", "")
        logql += f" |= `{escaped}`"
    if level in {"error", "warning", "critical"}:
        logql += f" |~ `(?i){level}`"

    page, page_size = parse_pagination(request.GET)
    max_log_page = max(1, (LOKI_MAX_LINES + page_size - 1) // page_size)
    page = min(page, max_log_page)

    now_ns = time.time_ns()
    try:
        anchor_ns = int(request.GET.get("anchor_ns", now_ns))
    except (TypeError, ValueError):
        anchor_ns = now_ns
    anchor_ns = max(1, min(anchor_ns, now_ns))
    before_raw = request.GET.get("before_ns")
    if page > 1 and not before_raw:
        page = 1
    try:
        end_ns = int(before_raw) if before_raw else anchor_ns
    except (TypeError, ValueError):
        end_ns = anchor_ns
    end_ns = max(1, min(end_ns, anchor_ns))
    start_ns = max(0, anchor_ns - range_seconds * 1_000_000_000)
    end_ns = max(start_ns, end_ns)
    client = LokiClient()
    query_limit = min(page_size + 1, LOKI_MAX_LINES)
    result = client.query_range(logql, start_ns=start_ns, end_ns=end_ns, limit=query_limit)
    if result is None:
        return JsonResponse(degraded("loki", "Log servisi müvəqqəti əlçatmazdır"))

    lines = []
    for stream in result:
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            try:
                ts_ns = int(ts)
            except (TypeError, ValueError):
                continue
            lines.append(
                {
                    "_ts_ns": ts_ns,
                    "ts": ts_ns // 1_000_000,  # ms
                    "container": labels.get("container", ""),
                    "line": redact_secrets(line[:1000]),
                }
            )
    lines.sort(key=lambda row: (row["_ts_ns"], row["container"], row["line"]), reverse=True)

    page_lines = lines[:page_size]
    has_next = len(lines) > page_size
    next_cursor_ns = max(1, page_lines[-1]["_ts_ns"] - 1) if has_next and page_lines else None
    for row in page_lines:
        row.pop("_ts_ns", None)
    total_exact = not has_next
    total = (page - 1) * page_size + len(page_lines) + int(has_next)
    total_pages = page + int(has_next)
    containers = client.labels_values("container") or []
    data = paginated_data(
        "lines",
        page_lines,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
        total_pages=total_pages,
        total_exact=total_exact,
        extra={
            "containers": containers,
            "anchor_ns": anchor_ns,
            "before_ns": end_ns,
            "next_cursor_ns": next_cursor_ns,
        },
    )
    return JsonResponse({"status": "ok", "data": data})


@require_GET
@monitoring_view_required
def incidents_api(request):
    status_filter = request.GET.get("status", "")
    scope = _scope(request)
    can_manage = bool(scope is None or scope.can_manage)
    qs = Incident.objects.all()
    if status_filter == "open":
        qs = qs.exclude(status=IncidentStatus.RESOLVED)
    elif status_filter:
        qs = qs.filter(status=status_filter)
    page, page_size = parse_pagination(request.GET)
    total = qs.count()
    page = clamp_page(page, total=total, page_size=page_size)
    qs = qs.order_by("-started_at", "-pk")
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
            "assigned_to": getattr(incident.assigned_to, "username", None) if can_manage else None,
            "resolution_note": incident.resolution_note,
        }
        for incident in qs.select_related("assigned_to")[(page - 1) * page_size : page * page_size]
    ]
    data = paginated_data(
        "incidents",
        rows,
        total=total,
        page=page,
        page_size=page_size,
        extra={"can_manage": can_manage},
    )
    return JsonResponse({"status": "ok", "data": data})


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
@monitoring_view_required
def security_events_api(request):
    """Hadisələr (``type``, ``ip``, ``page``, ``page_size``); ``ip`` verilibsə ``data.logins`` da (security_ip.py)."""
    try:
        ip_filter = parse_ip_filter(request.GET.get("ip"))
    except InvalidIpFilter as error:
        return JsonResponse({"status": "error", "error": "invalid_ip", "detail": str(error)}, status=400)
    qs = SecurityEvent.objects.select_related("user", "incident").filter(_org_filter(request))
    event_type = request.GET.get("type", "")
    if event_type:
        qs = qs.filter(event_type=event_type)
    if ip_filter is not None:
        qs = qs.filter(ip_filter.q())
    page, page_size = parse_pagination(request.GET)
    total = qs.count()
    page = clamp_page(page, total=total, page_size=page_size)
    qs = qs.order_by("-last_seen_at", "-pk")
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
        for event in qs[(page - 1) * page_size : page * page_size]
    ]
    extra = None
    if ip_filter is not None:
        extra = {"ip_filter": ip_filter.as_dict(), "logins": successful_logins(_scope(request), ip_filter)}
    data = paginated_data(
        "events",
        rows,
        total=total,
        page=page,
        page_size=page_size,
        extra=extra,
    )
    return JsonResponse({"status": "ok", "data": data})


def _bearer_token(request) -> str:
    """``Authorization: Bearer <token>`` başlığından tokeni çıxarır; yoxdursa boş sətir."""
    header = request.headers.get("Authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return credentials.strip()


@csrf_exempt
@require_POST
def alertmanager_webhook(request):
    """Alertmanager → insident axını. Token ilə qorunur, yalnız daxili şəbəkə.

    CSRF-exempt-dir çünki maşın-maşın sorğusudur; giriş nəzarəti paylaşılan
    token-lədir (ALERTMANAGER_WEBHOOK_TOKEN) və nginx bu path-i publik marşruta
    çıxarmır (app konteynerinə yalnız daxili şəbəkədən çatmaq olar).

    Token YALNIZ ``Authorization: Bearer <token>`` başlığından oxunur
    (2026-09-12, audit P2-6). Əvvəl ``?token=`` sorğu sətrində gəlirdi — sirr
    nginx/proxy access log-larına və ``Referer``-ə düşürdü. Sorğu sətrindəki
    token artıq QƏBUL EDİLMİR ki, köhnə konfiqurasiya səssizcə sızmağa davam
    etməsin; belə cəhd ayrıca log sətri ilə görünən olur.
    """
    expected = getattr(settings, "ALERTMANAGER_WEBHOOK_TOKEN", "") or ""
    provided = _bearer_token(request)
    if not expected or not hmac.compare_digest(expected, provided):
        if "token" in request.GET:
            logger.warning(
                "Alertmanager webhook: token sorğu sətrində gəlib — artıq qəbul edilmir, "
                "`Authorization: Bearer` başlığına keçin (uzaq=%s)",
                request.META.get("REMOTE_ADDR"),
            )
        else:
            logger.warning("Alertmanager webhook: yanlış token (uzaq=%s)", request.META.get("REMOTE_ADDR"))
        return HttpResponseForbidden("forbidden")

    try:
        # UnicodeDecodeError ValueError-un alt-sinifidir → tək ValueError kifayətdir.
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"detail": "invalid payload"}, status=400)

    from .incidents import ingest_alertmanager_payload

    result = ingest_alertmanager_payload(payload)
    return JsonResponse({"status": "ok", **result})
