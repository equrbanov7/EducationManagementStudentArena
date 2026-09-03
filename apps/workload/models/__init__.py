"""Dərs yükü modelləri — modul ölçü budcəsinə görə mövzu üzrə bölünüb."""

from .amendment import WorkloadAmendment, amendment_document_path
from .assignment import TeacherAssignment, TeacherWorkloadProfile
from .review import LoadObjection, TaskFacultySlice, TaskRowReview
from .task import TeachingTask, TeachingTaskRow

__all__ = [
    "LoadObjection",
    "TaskFacultySlice",
    "TaskRowReview",
    "TeacherAssignment",
    "TeacherWorkloadProfile",
    "TeachingTask",
    "TeachingTaskRow",
    "WorkloadAmendment",
    "amendment_document_path",
]
