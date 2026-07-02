from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.blog"

    def ready(self):
        # M2 (2026-07-02): profil bölmə implementasiyalarını accounts-un
        # profile_hooks registry-sinə qoş (bax apps/blog/profile_sections.py).
        from . import signals  # noqa: F401
        from . import profile_sections

        profile_sections.register_all()
