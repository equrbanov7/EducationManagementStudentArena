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
from .intensive_api import intensive_lookup
from .row_transfer_api import row_transfer, row_transfer_destinations
from .teacher_api import my_export, my_rows

__all__ = [
    "amend",
    "assign",
    "confirm",
    "curriculum",
    "intensive_lookup",
    "my_export",
    "my_rows",
    "options",
    "row_delete",
    "row_save",
    "row_transfer",
    "row_transfer_destinations",
    "rows",
    "task",
    "teachers",
    "unassign_view",
]
