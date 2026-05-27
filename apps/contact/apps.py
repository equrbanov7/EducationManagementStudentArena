from django.apps import AppConfig


class ContactConfig(AppConfig):
    """Public contact form app.

    Standalone, low-coupling app that exposes a public contact page,
    validates and rate-limits submissions, persists them, and dispatches
    a notification email to the configured site owner address.

    The app is intentionally NOT tenant-scoped: messages from any
    visitor (anonymous or authenticated, any organization) land in a
    single global inbox. RBAC for VIEWING submissions in admin is
    restricted to superusers via the admin registration.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contact"
    verbose_name = "Contact"
