from django.apps import AppConfig


class ExamsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exams"

    def ready(self):
        # Signal handlers keep derived exam access artifacts (student PINs)
        # synchronized when assignments change outside the exam form.
        from . import signals  # noqa: F401
