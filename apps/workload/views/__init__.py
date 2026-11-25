"""Dərs yükü JSON səthi (profil bölmələri buradan data alır)."""

from .confirm_api import confirm
from .distribution_api import (
    amend,
    assign,
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
from .split_wizard_api import split_wizard_journals, split_wizard_save, split_wizard_state
from .streams_api import patok_streams
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
    "patok_streams",
    "row_delete",
    "row_save",
    "row_transfer",
    "row_transfer_destinations",
    "rows",
    "split_wizard_journals",
    "split_wizard_save",
    "split_wizard_state",
    "task",
    "teachers",
    "unassign_view",
]
