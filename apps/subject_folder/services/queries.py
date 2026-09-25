"""UI üçün axtarış/süzgəc köməkçiləri — HAMISI məhdud (select_related/prefetch, aqreqat SQL-də).

Siyahı funksiyaları QuerySet qaytarır (UI özü səhifələyir); icazə süzgəci
queryset səviyyəsindədir (``access.visible_submissions_q``) — sətir-sətir
yoxlama YOXDUR, sorğu sayı sətir sayından asılı deyil.
"""

from __future__ import annotations

from django.db.models import Avg, Count, F, Func, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from core.search_text import tolerant_q  # kanonik API; burada geri-uyğun re-export (``__all__``)

from ..constants import FINAL_STATUSES, FolderStatus, SubmissionStatus, TaskKind
from ..errors import FolderError
from ..models import (
    FolderMaterial,
    FolderTask,
    FolderTopic,
    SimilarityMatch,
    SubjectFolder,
    Submission,
    SubmissionEvent,
    SubmissionFile,
)
from . import access, lookups

_PERSON_FIELDS = ("student__first_name", "student__last_name", "student__username")
_ORDERINGS = {
    "-submitted_at": ("-submitted_at", "-created_at"),
    "submitted_at": ("submitted_at", "created_at"),
    "student": ("student__last_name", "student__first_name", "student__username"),
    "status": ("status", "-submitted_at"),
    "-similarity": ("-similarity_max", "-submitted_at"),
    "task": ("task__kind", "task__slot_index", "task__order", "-submitted_at"),
}


def _count_rows(queryset):
    """Korrelyasiyalı ``COUNT(*)`` subquery — GROUP BY-sız (``Func`` aqreqat sayılmır)."""
    rows = queryset.order_by().annotate(n=Func(F("pk"), function="COUNT")).values("n")
    return Coalesce(Subquery(rows, output_field=IntegerField()), Value(0))


def _count_subquery(model, *, fk: str, **filters):
    rows = (
        model.objects.filter(**{fk: OuterRef("pk")}, **filters)
        .order_by()
        .values(fk)
        .annotate(n=Count("pk"))
        .values("n")
    )
    return Coalesce(Subquery(rows, output_field=IntegerField()), Value(0))


def list_folders(*, organization, actor, period=None, subject=None, statuses=None, search: str = ""):
    """Aktorun qovluqları (inzibatçı — təşkilatın hamısı) + sayğaclar (hər biri tək subquery)."""
    folders = SubjectFolder.objects.filter(organization=organization)
    if not lookups.is_org_admin(actor, organization):
        taught = lookups.taught_offerings_q(actor, prefix="assignments__offering__")
        folders = folders.filter(Q(owner_id=getattr(actor, "pk", None)) | (taught & Q(assignments__is_active=True)))
    if period is not None:
        folders = folders.filter(period=period)
    if subject is not None:
        folders = folders.filter(subject=subject)
    if statuses:
        folders = folders.filter(status__in=list(statuses))
    clause = tolerant_q(search, ("title", "subject__name"), compact_fields=("subject__code",))
    if clause is not None:
        folders = folders.filter(clause)
    pending = Submission.objects.filter(
        task__folder_id=OuterRef("pk"), status=SubmissionStatus.SUBMITTED, is_current=True
    )
    return (
        folders.distinct()
        .select_related("subject", "period", "owner")
        .annotate(
            topic_count=_count_subquery(FolderTopic, fk="folder", is_archived=False),
            material_count=_count_subquery(FolderMaterial, fk="folder", is_archived=False),
            selfwork_count=_count_subquery(FolderTask, fk="folder", is_archived=False, kind=TaskKind.SELFWORK),
            homework_count=_count_subquery(FolderTask, fk="folder", is_archived=False, kind=TaskKind.HOMEWORK),
            pending_review=_count_rows(pending),
        )
        .order_by("-period__start_date", "subject__name", "-created_at")
    )


def folder_contents(folder, *, actor) -> dict:
    """Qovluğun ağacı: mövzular → materiallar + tapşırıqlar (4 sorğu, ölçüdən asılı deyil).

    Tələbə (idarə etməyən, əməkdaş olmayan) YALNIZ dərc edilmiş, gizli olmayan
    məzmunu görür; auditoriyada olmayan aktor → ``FolderError("permission.denied")``.
    Nəticə: ``{"topics": [{"topic", "materials", "tasks"}], "general": {"materials", "tasks"},
    "is_staff_view": bool, "can_manage": bool}``.
    """
    staff_view = access.is_staff_viewer(actor, folder)
    if not staff_view and not access.is_folder_student(actor, folder):
        raise FolderError.of("permission.denied")
    topics = list(folder.topics.all().order_by("order", "week_no", "created_at"))
    materials = folder.materials.all().select_related("topic").order_by("order", "created_at")
    tasks = folder.tasks.all().prefetch_related("attachments").order_by("kind", "slot_index", "order", "created_at")
    if not staff_view:
        topics = [topic for topic in topics if not topic.is_archived]
        materials = materials.filter(is_published=True, is_archived=False).filter(
            Q(topic__isnull=True) | Q(topic__is_archived=False)
        )
        tasks = tasks.filter(is_published=True, is_archived=False).filter(
            Q(topic__isnull=True) | Q(topic__is_archived=False)
        )
    by_topic = {topic.pk: {"topic": topic, "materials": [], "tasks": []} for topic in topics}
    general = {"materials": [], "tasks": []}
    for material in materials:
        (by_topic.get(material.topic_id) or general)["materials"].append(material)
    for task in tasks:
        (by_topic.get(task.topic_id) or general)["tasks"].append(task)
    return {
        "topics": list(by_topic.values()),
        "general": general,
        "is_staff_view": staff_view,
        "can_manage": access.can_manage_folder(actor, folder),
    }


def list_materials(folder, *, actor, topic=None, kind=None, search: str = "", include_hidden: bool = False):
    staff_view = access.is_staff_viewer(actor, folder)
    if not staff_view and not access.is_folder_student(actor, folder):
        raise FolderError.of("permission.denied")
    rows = folder.materials.all().select_related("topic")
    if not (include_hidden and staff_view):
        rows = rows.filter(is_published=True, is_archived=False).filter(
            Q(topic__isnull=True) | Q(topic__is_archived=False)
        )
    if topic is not None:
        rows = rows.filter(topic=topic)
    if kind:
        rows = rows.filter(kind=kind)
    clause = tolerant_q(search, ("title", "description", "original_name", "code_text"))
    if clause is not None:
        rows = rows.filter(clause)
    return rows.order_by("topic__order", "order", "created_at")


def list_submissions(
    *,
    organization,
    actor,
    folder=None,
    task=None,
    assignment=None,
    offering=None,
    group=None,
    statuses=None,
    kind=None,
    student_query: str = "",
    date_from=None,
    date_to=None,
    flagged=None,
    journal_sync=None,
    late=None,
    current_only: bool = True,
    order: str = "-submitted_at",
):
    """Göndərişlər + süzgəclər. Qaralamalar (``draft``) müəllim siyahısına HEÇ VAXT düşmür.

    Annotasiyalar: ``file_count``, ``open_match_count`` (rədd edilməmiş oxşarlıqlar).
    """
    rows = Submission.objects.filter(access.visible_submissions_q(actor, organization)).exclude(
        status=SubmissionStatus.DRAFT
    )
    filters = {
        "task__folder": folder,
        "task": task,
        "assignment": assignment,
        "assignment__offering": offering,
        "assignment__offering__group": group,
        "kind": kind,
        "plagiarism_flagged": flagged,
        "is_late": late,
    }
    rows = rows.filter(**{key: value for key, value in filters.items() if value is not None})
    if statuses:
        rows = rows.filter(status__in=list(statuses))
    if journal_sync:
        rows = rows.filter(journal_sync_status__in=[journal_sync] if isinstance(journal_sync, str) else journal_sync)
    if current_only:
        rows = rows.filter(is_current=True)
    if date_from is not None:
        rows = rows.filter(submitted_at__date__gte=date_from)
    if date_to is not None:
        rows = rows.filter(submitted_at__date__lte=date_to)
    clause = tolerant_q(student_query, _PERSON_FIELDS)
    if clause is not None:
        rows = rows.filter(clause)
    open_matches = SimilarityMatch.objects.filter(
        Q(submission_a_id=OuterRef("pk")) | Q(submission_b_id=OuterRef("pk")), dismissed_at__isnull=True
    )
    return (
        rows.select_related(
            "task",
            "task__folder",
            "task__folder__subject",
            "assignment__offering__group",
            "student",
            "reviewed_by",
        )
        .annotate(
            file_count=_count_rows(SubmissionFile.objects.filter(submission_id=OuterRef("pk"))),
            open_match_count=_count_rows(open_matches),
        )
        .order_by(*_ORDERINGS.get(order, _ORDERINGS["-submitted_at"]))
    )


def status_counts(queryset) -> dict:
    """``{status: say, …, "total": say}`` — TƏK GROUP BY sorğusu."""
    counts = {status: 0 for status in SubmissionStatus.values}
    for row in queryset.order_by().values("status").annotate(n=Count("pk")):
        counts[row["status"]] = row["n"]
    counts["total"] = sum(counts[status] for status in SubmissionStatus.values)
    return counts


def task_progress(assignment) -> list[dict]:
    """Təyinatın hər tapşırığı üzrə sayğaclar (3 sorğu): auditoriya, göndərən, statuslar, bayraq, orta bal."""
    audience = lookups.audience_enrollments([assignment.offering_id]).count()
    tasks = list(assignment.folder.tasks.filter(is_archived=False).order_by("kind", "slot_index", "order"))
    stats = {
        row["task_id"]: row
        for row in Submission.objects.filter(assignment=assignment, is_current=True)
        .exclude(status=SubmissionStatus.DRAFT)
        .order_by()
        .values("task_id")
        .annotate(
            started=Count("pk"),
            submitted=Count("pk", filter=Q(status=SubmissionStatus.SUBMITTED)),
            returned=Count("pk", filter=Q(status=SubmissionStatus.RETURNED)),
            accepted=Count("pk", filter=Q(status=SubmissionStatus.ACCEPTED)),
            checked=Count("pk", filter=Q(status=SubmissionStatus.CHECKED)),
            rejected=Count("pk", filter=Q(status=SubmissionStatus.REJECTED)),
            flagged=Count("pk", filter=Q(plagiarism_flagged=True)),
            late=Count("pk", filter=Q(is_late=True)),
            avg_points=Avg("points"),
        )
    }
    result = []
    for task in tasks:
        row = stats.get(task.pk, {})
        started = row.get("started", 0)
        result.append(
            {
                "task": task,
                "audience": audience,
                "not_started": max(0, audience - started),
                **{key: row.get(key, 0) for key in ("submitted", "returned", "accepted", "checked", "rejected")},
                "flagged": row.get("flagged", 0),
                "late": row.get("late", 0),
                "avg_points": row.get("avg_points"),
            }
        )
    return result


def submission_detail(submission, *, actor) -> dict:
    """Bir göndərişin tam görünüşü: fayllar, zəncirin bütün cəhdləri, hadisələr, oxşarlıqlar.

    Oxşarlıq uyğunluqları və digər tələbənin kimliyi YALNIZ müəllim/əməkdaş görünüşündə
    verilir; tələbə öz işinin bayrağını görmür (``matches`` boşdur). Görmə hüququ
    olmayan aktor → ``FolderError("permission.denied")``.
    """
    if not access.can_view_submission(actor, submission):
        raise FolderError.of("permission.denied")
    staff = submission.student_id != getattr(actor, "pk", None)
    attempts = list(
        Submission.objects.filter(task_id=submission.task_id, enrollment_id=submission.enrollment_id)
        .prefetch_related("files")
        .order_by("attempt_no")
    )
    events = list(submission.events.all().order_by("created_at")) if staff else []
    if not staff:
        events = list(
            SubmissionEvent.objects.filter(
                submission__task_id=submission.task_id,
                submission__enrollment_id=submission.enrollment_id,
            )
            .exclude(kind__in=["plagiarism_flagged"])
            .order_by("created_at")
        )
    matches = []
    if staff:
        matches = list(
            SimilarityMatch.objects.filter(Q(submission_a=submission) | Q(submission_b=submission))
            .select_related(
                "submission_a__student", "submission_b__student", "submission_a__assignment__offering__group"
            )
            .order_by("-score")
        )
    can_review = access.can_review_assignment(actor, submission.assignment)
    actions = []
    if can_review and submission.is_current and submission.status == SubmissionStatus.SUBMITTED:
        actions = (
            ["accept", "return", "reject"] if submission.kind == TaskKind.SELFWORK else ["check", "return", "reject"]
        )
    elif can_review and submission.status == SubmissionStatus.REJECTED:
        actions = ["reopen"]
    return {
        "submission": submission,
        "attempts": attempts,
        "events": events,
        "matches": matches,
        "can_review": can_review,
        "actions": actions,
        "is_final": submission.status in FINAL_STATUSES,
    }


def folder_is_visible_to_students(folder) -> bool:
    return folder.status == FolderStatus.ACTIVE


__all__ = [
    "folder_contents",
    "folder_is_visible_to_students",
    "list_folders",
    "list_materials",
    "list_submissions",
    "status_counts",
    "submission_detail",
    "task_progress",
    "tolerant_q",
]
