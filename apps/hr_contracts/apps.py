from django.apps import AppConfig


class HrContractsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hr_contracts"
    label = "hr_contracts"
    verbose_name = "Əmək müqavilələri"

    def ready(self):
        # Müqavilə faylı qorunan mediadır — default DENY, checker ``media.check_file_access``.
        from apps.organizations.public import register_managed_settings_key
        from core.media_policies import register_media_policy

        from .constants import MEDIA_PREFIX, SNAPSHOT_KEY
        from .media import check_file_access

        register_media_policy(MEDIA_PREFIX, check_file_access)
        # «Müqavilələrim» menyu xülasəsinin yeganə yazıçısı ``sync_employee_snapshot``-dır — ``Organization.save()``
        # onu yaddaşdakı köhnə nüsxədən yazmasın (lost update; announcements ilə eyni qayda).
        register_managed_settings_key(SNAPSHOT_KEY)
