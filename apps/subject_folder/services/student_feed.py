"""Tələbə görünüşü — «Fənn qovluqlarım»: təyin olunmuş qovluqlar, tapşırıqlar və ÖZ vəziyyəti.

Sorğu sayı SABİTDİR (qovluq/tapşırıq sayından asılı deyil): qeydiyyatlar,
təyinatlar, tapşırıqlar, son tarixlər, cari cəhdlər — hər biri bir sorğu.
Tələbə yalnız AKTİV qovluğun, AKTİV təyinatın, dərc edilmiş və gizli
olmayan tapşırığını görür; sərbəst iş yalnız ``grades_selfwork`` təyinatında.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from ..constants import FINAL_STATUSES, FolderStatus, SubmissionStatus, TaskKind
from ..errors import FolderError
from ..models import FolderAssignment, FolderTask, Submission, TaskDeadline
from . import lookups
from .assignments import WINDOW_CLOSED, WINDOW_NOT_OPEN, window_state
from .submissions import resolve_enrollment


def _visible_tasks(folder_ids):
    return (
        FolderTask.objects.filter(folder_id__in=folder_ids, is_published=True, is_archived=False)
        .filter(Q(topic__isnull=True) | Q(topic__is_archived=False))
        .select_related("topic")
        .prefetch_related("attachments")
        .order_by("kind", "slot_index", "order", "created_at")
    )


def _task_state(task, assignment, deadline, current, now) -> dict:
    window = window_state(deadline, now=now)
    status = current.status if current is not None else None
    resubmission = status == SubmissionStatus.RETURNED
    blocked = None
    if status == SubmissionStatus.SUBMITTED:
        blocked = "submission.pending"
    elif status in FINAL_STATUSES:
        blocked = "submission.closed"
    elif window["state"] == WINDOW_NOT_OPEN:
        blocked = "deadline.not_open"
    elif window["state"] == WINDOW_CLOSED and not resubmission and not (current and current.attempt_no > 1):
        blocked = "deadline.passed"
    return {
        "task": task,
        "window": window,
        "submission": current,
        "status": status,
        "can_submit": blocked is None,
        "blocked_reason": blocked,
    }


def student_folders(*, organization, student, period=None) -> list[dict]:
    """Tələbənin qovluqları → ``[{"folder", "assignment", "offering", "tasks": [task_state…],
    "counts": {"selfwork", "homework", "open", "returned", "done"}}]``."""
    if not lookups.is_authenticated(student):
        return []
    enrollments = lookups.enrollment_model().objects.filter(
        organization=organization, student_id=student.pk, status=lookups.ENROLLED
    )
    if period is not None:
        enrollments = enrollments.filter(offering__period=period)
    offering_ids = list(enrollments.values_list("offering_id", flat=True))
    if not offering_ids:
        return []
    assignments = list(
        FolderAssignment.objects.filter(
            organization=organization,
            offering_id__in=offering_ids,
            is_active=True,
            folder__status=FolderStatus.ACTIVE,
        )
        .select_related("folder", "folder__subject", "folder__owner", "offering", "offering__period", "offering__group")
        .order_by("folder__subject__name", "assigned_at")
    )
    if not assignments:
        return []
    tasks_by_folder = {}
    for task in _visible_tasks({row.folder_id for row in assignments}):
        tasks_by_folder.setdefault(task.folder_id, []).append(task)
    deadlines = {
        (row.assignment_id, row.task_id): row for row in TaskDeadline.objects.filter(assignment__in=assignments)
    }
    currents = {
        (row.assignment_id, row.task_id): row
        for row in Submission.objects.filter(student_id=student.pk, assignment__in=assignments, is_current=True)
    }
    now = timezone.now()
    result = []
    for assignment in assignments:
        rows = []
        for task in tasks_by_folder.get(assignment.folder_id, []):
            if task.kind == TaskKind.SELFWORK and not assignment.grades_selfwork:
                continue
            key = (assignment.pk, task.pk)
            rows.append(_task_state(task, assignment, deadlines.get(key), currents.get(key), now))
        result.append(
            {
                "folder": assignment.folder,
                "assignment": assignment,
                "offering": assignment.offering,
                "tasks": rows,
                "counts": {
                    "selfwork": sum(1 for row in rows if row["task"].kind == TaskKind.SELFWORK),
                    "homework": sum(1 for row in rows if row["task"].kind == TaskKind.HOMEWORK),
                    "open": sum(1 for row in rows if row["can_submit"] and row["status"] != SubmissionStatus.RETURNED),
                    "returned": sum(1 for row in rows if row["status"] == SubmissionStatus.RETURNED),
                    "done": sum(1 for row in rows if row["status"] in FINAL_STATUSES),
                },
            }
        )
    return result


def student_task_view(task, assignment, student) -> dict:
    """Bir tapşırığın tələbə səhifəsi: şərt, qoşmalar, pəncərə, BÜTÜN cəhdləri (rəylə), düymə vəziyyəti.

    Tələbə bu təyinatın auditoriyasında deyilsə ``FolderError`` (``audience.not_enrolled`` və s.).
    Oxşarlıq bayrağı və müəllimin daxili qeydləri burada YOXDUR.
    """
    enrollment = resolve_enrollment(task, assignment, student)
    attempts = list(
        Submission.objects.filter(task=task, enrollment=enrollment).prefetch_related("files").order_by("attempt_no")
    )
    current = next((row for row in attempts if row.is_current), None)
    deadline = TaskDeadline.objects.filter(assignment=assignment, task=task).first()
    state = _task_state(task, assignment, deadline, current, timezone.now())
    return {
        **state,
        "assignment": assignment,
        "attachments": list(task.attachments.all()),
        "attempts": attempts,
        "enrollment": enrollment,
    }


def can_student_open(task, assignment, student) -> bool:
    try:
        resolve_enrollment(task, assignment, student)
    except FolderError:
        return False
    return True


__all__ = ["can_student_open", "student_folders", "student_task_view"]
