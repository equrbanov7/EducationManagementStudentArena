"""Dərs yükü JSON səthi (profil bölmələri buradan data alır)."""

from .distribution_api import (
    amend,
    assign,
    confirm,
    curriculum,
    options,
    row_delete,
    row_save,
    rows,
    task,
    teachers,
    unassign_view,
)
from .teacher_api import my_export, my_rows

__all__ = [
    "amend",
    "assign",
    "confirm",
    "curriculum",
    "my_export",
    "my_rows",
    "options",
    "row_delete",
    "row_save",
    "rows",
    "task",
    "teachers",
    "unassign_view",
]
