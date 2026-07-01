"""courses models — köhnə models.py-nin geriyə-uyğun fasad paketi.
Bütün modellər burada re-export olunur ki, `from apps.courses.models import X`
və Django model reyestri (app_label=courses) dəyişmədən işləsin."""

from ._base import User  # noqa: F401
from .content import CourseResource, CourseTopic  # noqa: F401
from .course import Course  # noqa: F401
from .enrollment import CourseGroup, CourseInstructor, CourseMembership  # noqa: F401

__all__ = [
    "Course",
    "CourseGroup",
    "CourseInstructor",
    "CourseMembership",
    "CourseResource",
    "CourseTopic",
]
