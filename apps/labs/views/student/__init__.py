"""Tələbə səthi (F2 rol-skeleti, 2026-07-02)."""

from .endpoints import lab_detail, my_lab_answers
from .submissions import auto_save_answer, submit_lab

__all__ = ["lab_detail", "my_lab_answers", "auto_save_answer", "submit_lab"]
