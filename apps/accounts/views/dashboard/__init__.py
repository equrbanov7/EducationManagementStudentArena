"""
Dashboard views package.

Split out of a single ~1,020-line ``dashboard.py`` module. Views are grouped by
audience/concern; this ``__init__`` re-exports them so existing imports
(``from .dashboard import ...`` in ``views/__init__.py``, ``views.dashboard``
in the URLConf) keep working unchanged.

Modules:
* ``dispatch`` — ``dashboard`` role dispatcher
* ``teacher``  — ``teacher_dashboard``, ``grading_queue``
* ``student``  — ``student_dashboard``, ``assigned_exams``, ``assigned_courses``,
  ``my_results``, ``pending_answers``
* ``results``  — ``my_result_detail``
* ``review``   — ``pending_review``, ``pending_review_detail``,
  ``review_results``, ``review_result_detail``
"""

from .dispatch import cabinet_entry, dashboard, resolve_cabinet_url
from .results import my_result_detail
from .review import (
    pending_review,
    pending_review_detail,
    review_result_detail,
    review_results,
)
from .student import (
    assigned_courses,
    assigned_exams,
    my_results,
    pending_answers,
    student_dashboard,
)
from .teacher import grading_queue, teacher_dashboard

__all__ = [
    "dashboard",
    "cabinet_entry",
    "resolve_cabinet_url",
    "teacher_dashboard",
    "student_dashboard",
    "grading_queue",
    "assigned_exams",
    "assigned_courses",
    "my_results",
    "pending_answers",
    "my_result_detail",
    "pending_review",
    "pending_review_detail",
    "review_results",
    "review_result_detail",
]
