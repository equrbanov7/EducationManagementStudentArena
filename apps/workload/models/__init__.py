"""Dərs yükü modelləri — modul ölçü budcəsinə görə mövzu üzrə bölünüb."""

from .amendment import WorkloadAmendment, amendment_document_path
from .assignment import TeacherAssignment, TeacherWorkloadProfile
from .task import TeachingTask, TeachingTaskRow

__all__ = [
    "TeacherAssignment",
    "TeacherWorkloadProfile",
    "TeachingTask",
    "TeachingTaskRow",
    "WorkloadAmendment",
    "amendment_document_path",
]
