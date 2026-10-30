from django.apps import AppConfig


class WorkloadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workload"
    verbose_name = "Dərs yükü"

    def ready(self):
        from apps.registrar.public import register_teacher_journal_assignments
        from core.group_identity import register_alias_provider

        from .services.group_aliases import verified_aliases
        from .services.journal_assignments import teacher_journal_assignments

        register_alias_provider(verified_aliases)
        register_teacher_journal_assignments(teacher_journal_assignments)
