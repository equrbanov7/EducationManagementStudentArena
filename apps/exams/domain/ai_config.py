"""
Singleton model for platform-wide AI configuration.

SuperAdmins manage this via the profile sidebar.  AI services read it
through ``get_ai_config()`` which caches the row for 60 seconds so
the DB is hit at most once per minute even under heavy traffic.
"""

from django.core.cache import cache
from django.core.validators import RegexValidator
from django.db import models

_CACHE_KEY = "ai_config_singleton"
_CACHE_TTL = 60  # seconds


class AIConfiguration(models.Model):
    """Platform-wide AI settings (singleton — only one row ever exists)."""

    # ── Feature toggle ─────────────────────────────────────────────
    enabled = models.BooleanField(
        default=True,
        help_text="AI funksiyalarını bütün platforma üzrə aktiv/deaktiv et.",
    )

    # ── Per-user rate limit ────────────────────────────────────────
    rate_limit = models.CharField(
        max_length=20,
        default="100/1h",
        validators=[
            RegexValidator(
                regex=r"^\d+/\d*[smhd]$",
                message='Format: "100/1h", "50/30m", "200/1d"',
            ),
        ],
        help_text='Hər istifadəçi üçün AI sorğu limiti.  Format: "say/müddət" (məs. "100/1h").',
    )

    # ── Model preferences ──────────────────────────────────────────
    MODEL_CHOICES = [
        ("gemini-2.5-flash", "Gemini 2.5 Flash (orta keyfiyyət, ucuz)"),
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (sürətli, ən ucuz)"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro (yüksək keyfiyyət, bahalı)"),
    ]

    summary_model = models.CharField(
        max_length=50,
        default="gemini-2.5-flash",
        choices=MODEL_CHOICES,
        help_text="Statistika xülasəsi üçün istifadə olunan model.",
    )

    grading_model = models.CharField(
        max_length=50,
        default="gemini-2.5-flash",
        choices=MODEL_CHOICES,
        help_text="Yazılı cavab qiymətləndirmə üçün istifadə olunan model.",
    )

    assistant_model = models.CharField(
        max_length=50,
        default="gemini-2.5-flash",
        choices=MODEL_CHOICES,
        help_text="AI Assistant (söhbət) üçün istifadə olunan model.",
    )

    # ── Budget ─────────────────────────────────────────────────────
    monthly_budget = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=5.00,
        help_text="Aylıq AI büdcəsi ($). Yalnız məlumat məqsədlidir.",
    )

    # ── Meta ───────────────────────────────────────────────────────
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "exams"
        verbose_name = "AI Configuration"
        verbose_name_plural = "AI Configuration"

    def __str__(self):
        return f"AI Config (rate={self.rate_limit}, enabled={self.enabled})"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(_CACHE_KEY)

    @classmethod
    def load(cls) -> "AIConfiguration":
        """Return the singleton instance, creating it with defaults if needed."""
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached
        obj, _ = cls.objects.get_or_create(pk=1)
        cache.set(_CACHE_KEY, obj, _CACHE_TTL)
        return obj


def get_ai_config() -> AIConfiguration:
    """Shortcut used by AI services to read the current configuration."""
    return AIConfiguration.load()
