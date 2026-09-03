from django.apps import AppConfig


class LegacyImportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.legacy_import"
    verbose_name = "Legacy import control plane"
