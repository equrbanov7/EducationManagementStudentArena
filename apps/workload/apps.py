from django.apps import AppConfig


class WorkloadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workload"
    verbose_name = "Dərs yükü"

    def ready(self):
        from core.group_identity import register_alias_provider

        from .services.group_aliases import verified_aliases

        register_alias_provider(verified_aliases)
