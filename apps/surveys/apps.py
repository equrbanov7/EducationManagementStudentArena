from django.apps import AppConfig


class SurveysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.surveys"
    label = "surveys"
    verbose_name = "Anonim sorğular"

    def ready(self):
        from apps.organizations.public import register_managed_settings_key

        # `registrar.journal_close.journal_closed` → kampaniyanın avtomatik açılışı.
        from . import receivers  # noqa: F401
        from .constants import GATE_SNAPSHOT_KEY

        # Qapı xülasəsinin yeganə yazıçısı `sync_gate_snapshot`-dır — `Organization.save()`
        # onu yaddaşdakı köhnə nüsxədən yazmasın (lost update, 2026-10-07).
        register_managed_settings_key(GATE_SNAPSHOT_KEY)
