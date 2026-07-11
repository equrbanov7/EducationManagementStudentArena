from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"
    verbose_name = "Organizations"

    def ready(self):
        """Import signal handlers when app is ready."""
        try:
            import apps.organizations.signals  # noqa
        except ImportError:
            pass

        # EXAM-P0-01: DB rolunun RLS-ə tabe olduğunu yoxlayan system check.
        import apps.organizations.checks  # noqa: F401
