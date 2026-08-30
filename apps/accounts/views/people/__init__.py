"""«Müəllimlər» / «Tələbələr» kataloqu — view fasadı (SPA bölmə + JSON endpoint)."""

from .actions import people_action
from .api import people_detail, people_list, people_options
from .section import build_people_section, build_people_students_section, build_people_teachers_section

__all__ = [
    "build_people_section",
    "build_people_students_section",
    "build_people_teachers_section",
    "people_action",
    "people_detail",
    "people_list",
    "people_options",
]
