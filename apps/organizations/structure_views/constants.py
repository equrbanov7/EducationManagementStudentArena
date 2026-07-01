"""structure_views paketi — constants."""

from core.constants import OrgUnitType

KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)


TEACHER_ROLE_NAMES = ("teacher", "assistant", "assistant_teacher", "instructor", "collaborator")


HEAD_CANDIDATE_MIN_LEVEL = 40


FACULTY_PAGE_SIZE = 9


KAFEDRA_PAGE_SIZE = 9


_SORT_OPTIONS = {
    "name": ("name",),
    "-name": ("-name",),
    "newest": ("-created_at", "name"),
    "oldest": ("created_at", "name"),
}
