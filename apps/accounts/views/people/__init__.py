"""«Müəllimlər» / «Tələbələr» kataloqu — view fasadı (SPA bölmə + JSON endpoint)."""

from .academic import people_academic_groups, people_student_card, people_transfer_preview
from .actions import people_action
from .analytics import people_analytics, people_analytics_ai
from .api import people_detail, people_list, people_options
from .section import build_people_section, build_people_students_section, build_people_teachers_section

__all__ = [
    "build_people_section",
    "build_people_students_section",
    "build_people_teachers_section",
    "people_academic_groups",
    "people_action",
    "people_analytics",
    "people_analytics_ai",
    "people_detail",
    "people_list",
    "people_options",
    "people_student_card",
    "people_transfer_preview",
]
