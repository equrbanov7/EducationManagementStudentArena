"""
courses/apps.py
───────────────
Courses app konfigürasyonu.
"""

from django.apps import AppConfig


class CoursesConfig(AppConfig):
    """Courses app-ı üçün Django config."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'courses'
    verbose_name = 'Kurslar İdarəetməsi'
    
    def ready(self):
        """
        App yüklənəndə çalışacaq kodlar.
        İleridə signals əlavə edə bilərik.
        """
        pass
    
    
from django.apps import AppConfig

class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "courses"
    verbose_name = "Kurslar İdarəetməsi"

    def ready(self):
        # ✅ courses/signals.py yüklənsin
        import courses.signals  # noqa

