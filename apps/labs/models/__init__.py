"""labs models — köhnə models.py-nin geriyə-uyğun fasad paketi."""

from ._base import User, secure_random  # noqa: F401
from .assignment import LabAnswer, LabAssignment, LabSubmission  # noqa: F401
from .lab import LAB_MAX_FILE_SIZE_MB, Lab, LabBlock, LabQuestion, clamp_lab_max_file_size_mb  # noqa: F401

__all__ = [
    "LAB_MAX_FILE_SIZE_MB",
    "Lab",
    "LabAnswer",
    "LabAssignment",
    "LabBlock",
    "LabQuestion",
    "LabSubmission",
    "clamp_lab_max_file_size_mb",
]
