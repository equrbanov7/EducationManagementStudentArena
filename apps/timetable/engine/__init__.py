"""Avtomatik dərs cədvəli mühərriki — saf Python, Django-dan asılı DEYİL.

Giriş: :class:`Instance` (hadisələr, resurslar, domenlər); çıxış: :class:`Result`
(hər hadisənin ``(xana, həftə)`` dəyəri və ya yerləşdirilməmə səbəbi, otaq
təklifi, KPI-lar). Django tərəfi (``apps.timetable.sources``) bazanı bu modelə
çevirir; mühərrik bazaya heç nə yazmır.
"""

from .patterns import weekly_load, weekly_pattern
from .solver import DEFAULT_SOLVER, SOLVERS, LocalSearchSolver, get_solver, solve
from .types import (
    LEVEL_DISCOURAGED,
    LEVEL_NEUTRAL,
    LEVEL_PREFERRED,
    LEVEL_UNAVAILABLE,
    WEEK_BOTH,
    WEEK_CODES,
    WEEK_EVEN,
    WEEK_FROM_CODE,
    WEEK_ODD,
    WEEKS_OF,
    Building,
    Cohort,
    Event,
    Instance,
    Params,
    Result,
    Room,
    Teacher,
    Weights,
)
from .verify import check

__all__ = [
    "DEFAULT_SOLVER",
    "LEVEL_DISCOURAGED",
    "LEVEL_NEUTRAL",
    "LEVEL_PREFERRED",
    "LEVEL_UNAVAILABLE",
    "SOLVERS",
    "WEEKS_OF",
    "WEEK_BOTH",
    "WEEK_CODES",
    "WEEK_EVEN",
    "WEEK_FROM_CODE",
    "WEEK_ODD",
    "Building",
    "Cohort",
    "Event",
    "Instance",
    "LocalSearchSolver",
    "Params",
    "Result",
    "Room",
    "Teacher",
    "Weights",
    "check",
    "get_solver",
    "solve",
    "weekly_load",
    "weekly_pattern",
]
