"""seed_group_demo_data komandası üçün mixin köməkçiləri.

Django komanda discovery yalnız commands/ altındakı `_`-siz .py faylları
skan edir, ona görə bu `_`-prefiksli paket komanda kimi qəbul edilmir.
Command sinfi bu mixin-ləri MRO ilə birləşdirir (seed_group_demo_data.py)."""

from .courses import CoursesSeedMixin  # noqa: F401
from .exams import ExamsSeedMixin  # noqa: F401
from .users import UsersSeedMixin  # noqa: F401

__all__ = ["UsersSeedMixin", "CoursesSeedMixin", "ExamsSeedMixin"]
