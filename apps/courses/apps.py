"""
courses/apps.py
───────────────
Courses app konfigürasyonu.
"""

from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courses"
    verbose_name = "Kurslar İdarəetməsi"

    def ready(self):
        # ✅ courses/signals.py yüklənsin
        from apps.courses import signals  # noqa
