"""Avtomatik cədvəl modelləri — giriş (əlçatanlıq, növbə) və işləmə (run, qaralama)."""

from .inputs import GroupTimePolicy, TeacherAvailability
from .runs import TimetableDraftSlot, TimetableRun

__all__ = ["GroupTimePolicy", "TeacherAvailability", "TimetableDraftSlot", "TimetableRun"]
