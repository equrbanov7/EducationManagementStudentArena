from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoring"
    verbose_name = "Sistem Monitorinqi"

    def ready(self):  # pragma: no cover - import side effects
        # Təhlükəsizlik hadisəsi siqnalları (uğursuz login və s.).
        from . import security  # noqa: F401

        # Celery/backup gauge-ları scrape zamanı cache-dən oxuyan kollektor.
        from .collectors import register_cache_collector

        register_cache_collector()
