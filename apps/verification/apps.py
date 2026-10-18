from django.apps import AppConfig


class VerificationConfig(AppConfig):
    """Sənəd yoxlaması (sahib 2026-10-18): rəsmi sənədin QR + kodu, publik ``/yoxla/<kod>/`` səhifəsi."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.verification"
    label = "verification"
    verbose_name = "Sənəd yoxlaması"
