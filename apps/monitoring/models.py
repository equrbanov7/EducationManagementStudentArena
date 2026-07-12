"""Sistem Monitorinqi modelləri: Incident + SecurityEvent.

Platforma-səviyyə cədvəllərdir (tenant-scoped deyil) — onlara giriş yalnız
superadmin API-ları üzərindəndir (permissions.superadmin_monitoring_required).
Heç bir sahədə həssas məzmun (parol, token, PIN, imtahan cavabı) saxlanmır;
``request_info`` yalnız təhlükəsiz metadata (path, method, user-agent) daşıyır.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class IncidentStatus(models.TextChoices):
    OPEN = "open", "Açıq"
    ACKNOWLEDGED = "acknowledged", "Qəbul edilib"
    INVESTIGATING = "investigating", "Araşdırılır"
    MONITORING = "monitoring", "İzlənilir"
    RESOLVED = "resolved", "Həll olunub"
    SILENCED = "silenced", "Səssizləşdirilib"


class Severity(models.TextChoices):
    INFO = "info", "Məlumat"
    LOW = "low", "Aşağı"
    MEDIUM = "medium", "Orta"
    HIGH = "high", "Yüksək"
    CRITICAL = "critical", "Kritik"


class Incident(models.Model):
    """Alertmanager webhook-undan və ya daxili mənbədən yaranan insident."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=16, choices=IncidentStatus.choices, default=IncidentStatus.OPEN, db_index=True)
    # Mənbə: "alertmanager" | "security" | "manual".
    source = models.CharField(max_length=32, default="alertmanager")
    service = models.CharField(max_length=100, blank=True)
    alert_rule = models.CharField(max_length=150, blank=True, db_index=True)
    environment = models.CharField(max_length=32, default="production")

    # Alertmanager qrupunun dublikat açarı (alertname+instance əsaslı).
    fingerprint = models.CharField(max_length=128, db_index=True)

    started_at = models.DateTimeField(default=timezone.now)
    detected_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_incidents_assigned",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_incidents_acknowledged",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_incidents_resolved",
    )
    resolution_note = models.TextField(blank=True)

    # Alertmanager label/annotasiyaları (təhlükəsiz, aşağı həcmli metadata).
    labels = models.JSONField(default=dict, blank=True)
    annotations = models.JSONField(default=dict, blank=True)
    # Bildiriş çatdırılma jurnalı: [{"channel","at","ok","note"}...] (≥90 gün
    # saxlama insidentin öz retention-u ilə təmin olunur).
    delivery_log = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["fingerprint", "status"]),
            models.Index(fields=["severity", "-started_at"]),
        ]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title} ({self.get_status_display()})"

    @property
    def duration_seconds(self) -> int | None:
        end = self.resolved_at or timezone.now()
        if not self.started_at:
            return None
        return max(0, int((end - self.started_at).total_seconds()))

    def add_delivery(self, channel: str, ok: bool, note: str = ""):
        self.delivery_log = (self.delivery_log or []) + [
            {"channel": channel, "at": timezone.now().isoformat(), "ok": ok, "note": note[:200]}
        ]


class SecurityEventType(models.TextChoices):
    LOGIN_FAILED = "login_failed", "Uğursuz giriş"
    LOGIN_BRUTE_FORCE = "login_brute_force", "Brute-force nümunəsi"
    SUPERADMIN_LOGIN = "superadmin_login", "Superadmin girişi"
    SUPERADMIN_LOGIN_FAILED = "superadmin_login_failed", "Superadmin uğursuz girişi"
    UNAUTHORIZED_MONITORING = "unauthorized_monitoring", "İcazəsiz monitorinq cəhdi"
    PERMISSION_DENIED_SPIKE = "permission_denied_spike", "İcazə rədd sıçrayışı"
    RATE_LIMIT = "rate_limit", "Rate-limit hadisəsi"
    EXAM_PIN_ABUSE = "exam_pin_abuse", "İmtahan PIN sui-istifadəsi"
    CONFIG_CHANGE = "config_change", "Kritik konfiqurasiya dəyişikliyi"
    OTHER = "other", "Digər"


class SecurityEvent(models.Model):
    """Superadmin-only Təhlükəsizlik Hadisələri bölməsinin qeydi."""

    event_type = models.CharField(max_length=40, choices=SecurityEventType.choices, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.LOW)
    source_service = models.CharField(max_length=64, default="django")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_security_events",
    )
    # İstifadəçi hələ mövcud deyilsə (uğursuz login) yalnız daxil edilən ad.
    username_hint = models.CharField(max_length=150, blank=True)
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.SET_NULL)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # Yalnız təhlükəsiz sorğu metadata-sı: {"path","method","user_agent"}.
    request_info = models.JSONField(default=dict, blank=True)
    message = models.CharField(max_length=500, blank=True)
    count = models.PositiveIntegerField(default=1)

    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="monitoring_security_events_resolved",
    )
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["event_type", "-last_seen_at"]),
            models.Index(fields=["ip_address", "event_type"]),
        ]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.get_event_type_display()} ×{self.count}"
