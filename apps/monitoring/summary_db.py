"""Xülasə paneli üçün BAZA göstəriciləri — əhatəli, məhdud sorğularla (2026-10-01).

Hər funksiya sabit sayda (1–2) aqreqat sorğu işlədir; siyahı qaytaran yerlər
sərt ``[:N]`` limitlidir. Nəticədə yalnız SAYLAR var — heç bir istifadəçi adı,
e-poçt və ya IP ünvanı qaytarılmır (xülasə AI təhlilinə də gedir).

Əhatə (``MonitoringScope``):
* platforma (superadmin) — bütün tenantlar (çağıran ``bypass_rls()`` içindədir);
* icazəli üzv (RİM rəhbəri) — yalnız ÖZ təşkilatı + org-suz (platforma)
  sətirlər. RLS onsuz da belə süzür; burada açıq ORM filtri də qoyulur
  (müdafiə dərinliyi + RLS-siz test bazası).
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Incident, IncidentStatus, SecurityEvent
from .wording import alert_title

#: Audit jurnalındakı təhlükəsizlik rədd növləri (hamısı ``action=deny``).
NETWORK_ZONE_TYPES = ("network_zone_deny",)
PROFANITY_TYPES = ("moderation.profanity_blocked",)
ADMIN_TYPES = (
    "admin_ip_deny",
    "admin_login_failed",
    "admin_login_rate_limit",
    "admin_otp_failed",
    "admin_otp_verify_rate_limited",
    "admin_otp_resend_rate_limited",
)
_DENY_ACTIONS = ("deny", "access_denied")
_INCIDENT_GROUP_LIMIT = 8
_INCIDENT_ROW_LIMIT = 200


def _org_q(scope, field: str = "organization_id") -> Q:
    if scope.platform:
        return Q()
    return Q(**{f"{field}__isnull": True}) | Q(**{field: scope.organization_id})


def database_ping() -> dict:
    """``SELECT 1`` gecikməsi (ms); xətada ``ok=False``."""
    started = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover - baza düşübsə xülasə yenə də qaytarılmalıdır
        return {"ok": False, "ms": None}
    return {"ok": True, "ms": round((time.monotonic() - started) * 1000, 1)}


def security_counts(scope, now) -> dict:
    """24 saat / 7 gün pəncərələrində təhlükəsizlik hadisələrinin sayları (2 sorğu)."""
    from apps.audit.models import AuditLog

    since_day = now - timedelta(hours=24)
    since_week = now - timedelta(days=7)

    def _sum(event_type: str, since):
        return Sum("count", filter=Q(event_type=event_type, last_seen_at__gte=since))

    events = SecurityEvent.objects.filter(_org_q(scope), last_seen_at__gte=since_week).aggregate(
        failed_logins_24h=_sum("login_failed", since_day),
        failed_logins_7d=_sum("login_failed", since_week),
        brute_force_24h=Count("id", filter=Q(event_type="login_brute_force", last_seen_at__gte=since_day)),
        brute_force_7d=Count("id", filter=Q(event_type="login_brute_force")),
        superadmin_failed_24h=_sum("superadmin_login_failed", since_day),
        superadmin_failed_7d=_sum("superadmin_login_failed", since_week),
        unauthorized_monitoring_24h=_sum("unauthorized_monitoring", since_day),
        unauthorized_monitoring_7d=_sum("unauthorized_monitoring", since_week),
    )

    special = NETWORK_ZONE_TYPES + PROFANITY_TYPES + ADMIN_TYPES
    day = Q(created_at__gte=since_day)
    audit = AuditLog.objects.filter(_org_q(scope), action__in=_DENY_ACTIONS, created_at__gte=since_week).aggregate(
        network_zone_24h=Count("id", filter=Q(resource_type__in=NETWORK_ZONE_TYPES) & day),
        network_zone_7d=Count("id", filter=Q(resource_type__in=NETWORK_ZONE_TYPES)),
        profanity_24h=Count("id", filter=Q(resource_type__in=PROFANITY_TYPES) & day),
        profanity_7d=Count("id", filter=Q(resource_type__in=PROFANITY_TYPES)),
        admin_denials_24h=Count("id", filter=Q(resource_type__in=ADMIN_TYPES) & day),
        admin_denials_7d=Count("id", filter=Q(resource_type__in=ADMIN_TYPES)),
        permission_denials_24h=Count("id", filter=~Q(resource_type__in=special) & day),
        permission_denials_7d=Count("id", filter=~Q(resource_type__in=special)),
    )
    merged = {**events, **audit}
    return {key: int(value or 0) for key, value in merged.items()}


def exam_activity(scope, now) -> dict:
    """«İndi imtahan gedirmi?» — exam_activity_probe ilə eyni saylar (3 sorğu)."""
    from apps.exams.models import Exam, ExamAttempt
    from apps.live_exam.models import LiveSession

    attempt_scope = Q() if scope.platform else Q(exam__organization_id=scope.organization_id)
    exam_scope = Q() if scope.platform else Q(organization_id=scope.organization_id)

    # Açıq cəhdlər qismən indeksdən (`examattempt_active_sweep_idx`) oxunur.
    open_stats = ExamAttempt.objects.filter(
        attempt_scope, status__in=("draft", "in_progress"), is_trial=False
    ).aggregate(
        open_attempts=Count("id"),
        open_recent=Count("id", filter=Q(started_at__gte=now - timedelta(hours=4))),
    )
    since = now - timedelta(minutes=15)
    flow = ExamAttempt.objects.filter(attempt_scope).filter(Q(started_at__gte=since) | Q(finished_at__gte=since))
    flow_stats = flow.aggregate(
        started_15m=Count("id", filter=Q(started_at__gte=since)),
        finished_15m=Count("id", filter=Q(finished_at__gte=since)),
    )
    active_exams = Exam.objects.filter(
        exam_scope, is_deleted=False, start_datetime__lte=now, end_datetime__gte=now
    ).count()
    live = (
        LiveSession.objects.filter(attempt_scope)
        .exclude(state=LiveSession.STATE_FINISHED)
        .filter(created_at__gte=now - timedelta(hours=6))
        .aggregate(
            live_active=Count("id"),
            live_running=Count("id", filter=Q(state__in=(LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL))),
        )
    )
    merged = {**open_stats, **flow_stats, **live, "active_exams": active_exams}
    return {key: int(value or 0) for key, value in merged.items()}


def user_activity(scope, now) -> dict:
    """Aktiv sessiyalar (təxmini) + bu gün/son saat daxil olanlar (2 sorğu)."""
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session

    # Sessiya hər ``SESSION_ACTIVITY_WRITE_INTERVAL`` (5 dəq) aktivlikdə yazılır və
    # ``expire_date`` = yazılma anı + ``SESSION_COOKIE_AGE`` olur. Deməli son 15
    # dəqiqədə yazılmış sessiyalar ≈ son 15 dəqiqədə aktiv olanlar (platforma üzrə).
    age = int(getattr(settings, "SESSION_COOKIE_AGE", 1209600))
    fresh_after = now + timedelta(seconds=age) - timedelta(minutes=15)
    active_sessions = Session.objects.filter(expire_date__gt=fresh_after).count()

    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    hour_ago = now - timedelta(hours=1)
    if scope.platform:
        logins = (
            get_user_model()
            .objects.filter(last_login__gte=min(today_start, hour_ago))
            .aggregate(
                logins_today=Count("id", filter=Q(last_login__gte=today_start)),
                logins_1h=Count("id", filter=Q(last_login__gte=hour_ago)),
            )
        )
    else:
        from apps.organizations.models import Membership

        logins = Membership.objects.filter(
            organization_id=scope.organization_id,
            is_active=True,
            user__last_login__gte=min(today_start, hour_ago),
        ).aggregate(
            logins_today=Count("user_id", distinct=True, filter=Q(user__last_login__gte=today_start)),
            logins_1h=Count("user_id", distinct=True, filter=Q(user__last_login__gte=hour_ago)),
        )
    return {
        "active_sessions_15m": active_sessions,
        "logins_today": int(logins["logins_today"] or 0),
        "logins_1h": int(logins["logins_1h"] or 0),
    }


def incidents_digest(now) -> dict:
    """Son 7 günün insidentləri — qaydaya görə qruplaşdırılmış, insan dilində (2 sorğu).

    İnsidentlər PLATFORMA səviyyəlidir (server/xidmət xəbərdarlıqları, tenant
    sahəsi yoxdur) — RİM rəhbəri də eyni siyahını OXU-ONLY görür.
    """
    open_stats = Incident.objects.exclude(status=IncidentStatus.RESOLVED).aggregate(
        open=Count("id"),
        critical_open=Count("id", filter=Q(severity="critical")),
    )
    rows = list(
        Incident.objects.filter(started_at__gte=now - timedelta(days=7))
        .order_by("-started_at", "-pk")
        .values("alert_rule", "title", "severity", "status", "started_at", "resolved_at")[:_INCIDENT_ROW_LIMIT]
    )
    groups: dict[str, dict] = {}
    for row in rows:
        key = row["alert_rule"] or row["title"]
        group = groups.get(key)
        is_open = row["status"] != IncidentStatus.RESOLVED
        if group is None:
            end = row["resolved_at"] or now
            groups[key] = group = {
                "rule": row["alert_rule"] or "",
                "title": alert_title(row["alert_rule"], row["title"]),
                "severity": row["severity"],
                "status": row["status"],
                "count": 0,
                "open": 0,
                "last_started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "last_duration_seconds": (
                    max(0, int((end - row["started_at"]).total_seconds())) if row["started_at"] else None
                ),
            }
        group["count"] += 1
        group["open"] += int(is_open)
        if row["severity"] == "critical":
            group["severity"] = "critical"
    # Açıq qruplar əvvəl, sonra həll olunmuşlar — hər ikisi ən yenidən köhnəyə.
    newest_first = sorted(groups.values(), key=lambda item: item["last_started_at"] or "", reverse=True)
    ordered = [group for group in newest_first if group["open"]] + [
        group for group in newest_first if not group["open"]
    ]
    return {
        "open": int(open_stats["open"] or 0),
        "critical_open": int(open_stats["critical_open"] or 0),
        "total_7d": len(rows),
        "groups": ordered[:_INCIDENT_GROUP_LIMIT],
    }


__all__ = ["database_ping", "exam_activity", "incidents_digest", "security_counts", "user_activity"]
