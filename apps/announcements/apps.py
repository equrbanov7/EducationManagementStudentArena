from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.announcements"
    label = "announcements"
    verbose_name = "Elanlar"

    def ready(self):
        # Xülasənin yeganə yazıçısı `services.snapshot.sync_snapshot`-dır — `Organization.save()`
        # onu yaddaşdakı köhnə nüsxədən yazmasın (lost update, 2026-10-07).
        from apps.organizations.public import register_managed_settings_key

        from .constants import SNAPSHOT_KEY

        register_managed_settings_key(SNAPSHOT_KEY)
