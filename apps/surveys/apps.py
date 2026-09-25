from django.apps import AppConfig


class SurveysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.surveys"
    label = "surveys"
    verbose_name = "Anonim sorğular"

    def ready(self):
        # `registrar.journal_close.journal_closed` → kampaniyanın avtomatik açılışı.
        from . import receivers  # noqa: F401
