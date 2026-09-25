"""Fənn qovluğu modelləri — hər cədvəldə birbaşa ``organization`` FK + RLS (0002)."""

from .assignment import FolderAssignment, TaskDeadline
from .folder import FolderTopic, SubjectFolder
from .materials import FolderMaterial
from .similarity import SimilarityMatch, SubmissionFingerprint
from .submission import Submission, SubmissionEvent, SubmissionFile
from .tasks import FolderTask, TaskAttachment

__all__ = [
    "FolderAssignment",
    "FolderMaterial",
    "FolderTask",
    "FolderTopic",
    "SimilarityMatch",
    "SubjectFolder",
    "Submission",
    "SubmissionEvent",
    "SubmissionFile",
    "SubmissionFingerprint",
    "TaskAttachment",
    "TaskDeadline",
]
