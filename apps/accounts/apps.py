from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        # ✅ accounts/signals.py yüklənsin
        # ✅ Import models to register UserProfile signals
        from apps.accounts import models  # noqa
        from apps.accounts import roles  # noqa - Attach role properties to User model
        from apps.accounts import signals  # noqa
