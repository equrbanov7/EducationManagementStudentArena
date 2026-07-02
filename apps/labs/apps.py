from django.apps import AppConfig


class LabsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.labs"

    def ready(self):
        # M2 (2026-07-02): kurs dashboard-una bölmə provider-ini qoş
        # (bax apps/courses/dashboard_sources.py — registry pattern).
        from apps.courses import dashboard_sources

        from .course_dashboard import build_course_dashboard_context

        dashboard_sources.register(build_course_dashboard_context)
