from django.apps import AppConfig
from django.utils.translation import pgettext_lazy


class AssignmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assignments"
    verbose_name = pgettext_lazy("assignment.app", "title")
