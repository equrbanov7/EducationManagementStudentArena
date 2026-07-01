"""labs models — köhnə models.py-nin geriyə-uyğun fasad paketi."""

from ._base import User, secure_random  # noqa: F401
from .assignment import LabAnswer, LabAssignment, LabSubmission  # noqa: F401
from .lab import Lab, LabBlock, LabQuestion  # noqa: F401

__all__ = [
    "Lab",
    "LabAnswer",
    "LabAssignment",
    "LabBlock",
    "LabQuestion",
    "LabSubmission",
]
