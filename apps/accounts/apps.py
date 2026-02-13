from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        # ✅ accounts/signals.py yüklənsin
        from apps.accounts import signals  # noqa
        # ✅ Import models to register UserProfile signals
        from apps.accounts import models  # noqa
