from django.apps import AppConfig


class ExamsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exams"

    def ready(self):
        # Signal handlers keep derived exam access artifacts (student PINs)
        # synchronized when assignments change outside the exam form.
        from . import signals  # noqa: F401

    def second_chance_provider(self):
        """Registrar 25% müraciətinin bağlanışı üçün «yenidən cəhd»in geri alınması (2026-10-19, HIGH-1).

        ``apps.registrar.retake_closure`` bunu app registry üzərindən (``django_apps.get_app_config("exams")``)
        çağırır — registrar → exams STATİK importu yoxdur (``scripts/module_deps.py``). Qaytarır:
        ``revoke_second_chance(...)``, ``blocking_attempt(...)`` və ``RevokeBlocked`` olan modul."""
        from .services import second_chance_revoke

        return second_chance_revoke
