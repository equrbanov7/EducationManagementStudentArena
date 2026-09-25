"""«Fənn qovluğu» modulunun PUBLIC fasadı — UI və digər modullar YALNIZ buradan istifadə edir.

Bütün yazı funksiyaları domen imtinasında :class:`FolderError` qaldırır:
``exc.code`` (sabit, məs. ``review.points_total_exceeded``), ``str(exc)`` (tərcümə
olunmuş mətn), ``exc.params``, ``exc.as_dict()``; ``exc.is_permission`` → HTTP 403,
qalan kodlar → 400. Fayl yoxlaması da ``upload.invalid`` kodu ilə gəlir.
``request=`` opsionaldır (audit IP/impersonation damğası üçün ötürün).

══════════════════════════════════════════════════════════════════════════════
1. QOVLUQ
══════════════════════════════════════════════════════════════════════════════
create_folder(*, organization, subject, owner, by_user, period=None, title="", description="",
              offering=None, request=None) -> (SubjectFolder, created: bool, sync_summary: dict)
    İdempotent (org, fənn, sahib, semestr). Müəllim yalnız özü üçün + tədris etdiyi fənn.
update_folder(folder, *, by_user, title=None, description=None, request=None) -> SubjectFolder
set_folder_status(folder, *, by_user, status: "draft"|"active"|"archived", request=None) -> SubjectFolder
resync_folder(folder, *, by_user, offering=None, request=None) -> sync_summary
clone_folder(source, *, by_user, period, request=None) -> (SubjectFolder, {"created", "topics", "materials",
              "homework", "selfwork"})
sync_summary = {"has_syllabus": bool, "version_id": str|None,
                "topics": {"created","updated","restored","archived","deleted"},
                "selfwork": {"option": "1x10"|"2x5"|"10x1"|None, "created": [slot…], "updated": […],
                             "archived": […], "deleted": […]}}

2. MÖVZULAR / MATERİALLAR / TAPŞIRIQLAR (sahib və ya inzibatçı)
create_topic(folder, *, by_user, title, description="", week_no=None) -> FolderTopic
update_topic(topic, *, by_user, title=None, description=None, week_no=None) -> FolderTopic
set_topic_hidden(topic, *, by_user, hidden=True) ; delete_topic(topic, *, by_user)  (yalnız boş, öz mövzu)
reorder_topics(folder, *, by_user, ordered_ids) -> int
create_material(folder, *, by_user, kind, title, description="", topic=None, file=None, url="", code_text="",
                code_language="", is_published=False) -> FolderMaterial
    kind: file|image (``file`` məcburi, ≤ SUBJECT_FOLDER_MATERIAL_MAX_MB, default 50) | link|video_link (``url``
    http/https) | code (``code_text``, MƏTN kimi saxlanılır) | note (``description``).
update_material(material, *, by_user, title=None, description=None, topic="__keep__", file=None, url=None,
                code_text=None, code_language=None) -> FolderMaterial
set_material_published(material, *, by_user, published) ; archive_material(material, *, by_user, archived=True)
reorder_materials(folder, *, by_user, ordered_ids) -> int
create_homework(folder, *, by_user, title, instructions="", topic=None, allowed_extensions=None, max_file_mb=None,
                max_files=None, allow_text_answer=True, allow_files=True, is_published=False) -> FolderTask
create_task(folder, *, by_user, kind, **fields)  — kind="selfwork" → ``task.selfwork_slots_fixed``
update_task(task, *, by_user, title=None, instructions=None, topic="__keep__", allowed_extensions=None,
            max_file_mb=None, max_files=None, allow_text_answer=None, allow_files=None) -> FolderTask
set_task_published(task, *, by_user, published)  — ilk dərcdə tələbələrə TOPLU bildiriş
archive_task(task, *, by_user, archived=True) ; delete_task(task, *, by_user)  (yalnız göndərişsiz ev tapşırığı)
reorder_tasks(folder, *, by_user, ordered_ids) ; add_task_attachment(task, *, by_user, file) -> TaskAttachment
remove_task_attachment(attachment, *, by_user)

3. TƏYİNAT / SON TARİX
assignable_offerings(folder, user) -> [{"offering", "assignment"|None, "is_active", "grades_selfwork",
                                        "selfwork_elsewhere"}]
assign_folder(folder, offerings, *, by_user) -> [{"assignment", "created", "reactivated", "warnings": [err dict]}]
    Qaralama qovluq ilk təyinatda AKTİV olur. Xəbərdarlıq kodları: ``assignment.selfwork_elsewhere``,
    ``assignment.selfwork_option_mismatch`` (təyinat aktivdir, amma sərbəst iş bu qrupda qovluqdan qəbul edilmir).
unassign(assignment, *, by_user) -> FolderAssignment
set_deadline(assignment, task, *, by_user, opens_at=None, due_at=None, late_policy="none"|"allow") -> TaskDeadline
set_deadline_for_all(task, *, by_user, opens_at=None, due_at=None, late_policy="none") -> [TaskDeadline]
clear_deadline(assignment, task, *, by_user) ; window_state(deadline_or_None, now=None) ->
    {"state": "open"|"not_open"|"late"|"closed", "opens_at", "due_at", "late_policy"}

4. TƏLƏBƏ
student_folders(*, organization, student, period=None) -> [{"folder", "assignment", "offering",
    "tasks": [task_state], "counts": {"selfwork","homework","open","returned","done"}}]   (5 sorğu, sabit)
student_task_view(task, assignment, student) -> {**task_state, "assignment", "attachments", "attempts",
    "enrollment"}   — auditoriyada deyilsə FolderError
task_state = {"task", "window", "submission" (cari cəhd|None), "status", "can_submit",
              "blocked_reason": None|"submission.pending"|"submission.closed"|"deadline.not_open"|"deadline.passed"}
save_draft(*, task, assignment, student, text=None, files=()) -> Submission (status draft)
submit(*, task, assignment, student, text=None, files=()) -> Submission (status submitted; commit-dən sonra
    plagiat yoxlaması + müəllimə xülasə)
remove_draft_file(file_row, *, student)

5. MÜƏLLİM BAXIŞI (qrupun canlı müəllimi / inzibatçı)
journal_preview(submission, points=None) -> {"slot_index", "slot_label", "task_title", "points", "max_points",
    "total_before", "total_after", "max_total", "remaining", "can_award", "error": err dict|None,
    "text": "Bu bal jurnala düşəcək: Sərbəst iş 2 · 4/5 (cəmi 9/10)",
    "journal": registrar ``selfwork_points.preview(...)`` dict (məs. {"blocked", "reason"}) | None}
accept(submission, *, by_user, points, feedback="") ; return_for_revision(submission, *, by_user, feedback)
check_homework(submission, *, by_user, feedback="") ; reject(submission, *, by_user, reason, feedback)
reopen(submission, *, by_user, feedback="")   (rədd → returned)
bulk_review(submissions, *, by_user, action: "accept"|"return"|"check"|"reject", points=None|dec|{id: dec},
            feedback="", reason="") -> {"ok": [id…], "failed": {id: err dict}}
REJECT_REASONS = RejectReason (late | plagiarism | off_topic | other)
dismiss_match(match, *, by_user, note="") ; restore_match(match, *, by_user)   — «plagiat deyil» qərarı

6. SİYAHI / AXTARIŞ (hamısı QuerySet və ya məhdud sorğulu dict)
list_folders(*, organization, actor, period=None, subject=None, statuses=None, search="") -> QuerySet[SubjectFolder]
    annotasiyalar: topic_count, material_count, selfwork_count, homework_count, pending_review
folder_contents(folder, *, actor) -> {"topics": [{"topic", "materials", "tasks"}], "general": {"materials","tasks"},
    "is_staff_view", "can_manage"}  (tələbə yalnız dərc edilmiş/gizli olmayanı görür)
list_materials(folder, *, actor, topic=None, kind=None, search="", include_hidden=False) -> QuerySet
list_submissions(*, organization, actor, folder=None, task=None, assignment=None, offering=None, group=None,
    statuses=None, kind=None, student_query="", date_from=None, date_to=None, flagged=None, journal_sync=None,
    late=None, current_only=True, order="-submitted_at"|"submitted_at"|"student"|"status"|"-similarity"|"task")
    -> QuerySet[Submission] (annotasiya: file_count, open_match_count; qaralama heç vaxt daxil deyil)
status_counts(queryset) -> {status: n, …, "total": n}
task_progress(assignment) -> [{"task", "audience", "not_started", "submitted", "returned", "accepted", "checked",
    "rejected", "flagged", "late", "avg_points"}]
submission_detail(submission, *, actor) -> {"submission", "attempts", "events", "matches" (yalnız müəllim/əməkdaş),
    "can_review", "actions": ["accept"|"check","return","reject"] | ["reopen"] | [], "is_final"}

7. İCAZƏ PREDİKATLARI: can_manage_folder, can_view_folder, can_view_material, can_view_task,
   can_review_assignment, can_view_submission, is_folder_student — hamısı (user, obj) -> bool.
   Endirmə URL-ləri: ``subject_folder:material_download`` (material_id), ``subject_folder:task_attachment_download``
   (attachment_id), ``subject_folder:submission_file_download`` (file_id) — faylın ``.url``-ini HEÇ VAXT göstərməyin.

8. PROFİL BÖLMƏ SLUG-LARI (bildiriş keçidləri bunlara gedir): SECTION_TEACHER="subject-folders",
   SECTION_REVIEW="subject-folder-review", SECTION_STUDENT="my-subject-folders"; sorğu parametrləri
   ``sf_folder``, ``sf_task``.

══════════════════════════════════════════════════════════════════════════════
9. REGISTRAR JURNAL HOOK MÜQAVİLƏSİ (registrar agenti yazır; bu app registrar-ı idxal etmir)
══════════════════════════════════════════════════════════════════════════════
Yer: ``apps/registrar/public_services.py`` → ``from . import selfwork_points`` və ``__all__``-a
``"selfwork_points"`` (``apps.registrar.public`` onu avtomatik re-eksport edir). Modul funksiyası::

    def record_points(*, offering, enrollment, slot_index: int, slot_title: str, max_points: Decimal,
                      points: Decimal, source_ref: str, by_user) -> tuple[bool, str]

* offering — ``registrar.CourseOffering``; enrollment — ``registrar.Enrollment`` (``status="enrolled"``);
* slot_index — sillabus slotu (1…N, N = 1/2/10); max_points — slotun maksimumu (10/5/1);
* points — ``Decimal``, 1 onluq, ``0 < points ≤ max_points``; bu app cəmi ≤ 10-u ARTIQ yoxlayıb;
* source_ref — ``"subject_folder.submission:<uuid>"`` (audit/izləmə üçün saxlayın);
* by_user — balı qəbul edən müəllim (``User``) və ya ``None``;
* SEMANTİKA: SET (upsert) açar ``(enrollment, slot_index)`` — təkrar çağırış idempotentdir, ARTIRMIR;
* qaytarır: ``(True, "")`` yazıldı; ``(False, "insan üçün səbəb")`` jurnal qəbul etmir (bağlıdır, dövr
  kilidlidir…) → bu app ``blocked`` + mesaj göstərir; istisna → ``pending``, sonra yenidən cəhd
  (``manage.py subject_folder_sync_journal --apply``, Celery ``subject_folder.sync_journal_pending``);
* hook öz savepoint-ində çağırılır; yazını ``transaction.atomic()`` ilə etmək kifayətdir.
OPSİONAL: ``selfwork_points.preview(*, offering, enrollment, slot_index, points) -> dict`` (YAZI YOXDUR) —
varsa ``journal_preview(...)["journal"]``-a qoyulur (UI qəbuldan əvvəl «jurnal bağlıdır» xəbərdarlığı göstərir);
xəta/yoxluq baxışı heç vaxt sındırmır.
Hook yoxdursa hər qəbul ``pending`` qalır və registrar tərəfi qoşulandan sonra əmr hamısını ötürür.
"""

from __future__ import annotations

from .constants import (  # noqa: F401
    JOURNAL_SYNC_TOKENS,
    SECTION_REVIEW,
    SECTION_STUDENT,
    SECTION_TEACHER,
    STATUS_TOKENS,
    CodeLanguage,
    EventKind,
    FolderStatus,
    JournalSyncStatus,
    LatePolicy,
    MaterialKind,
    PlagiarismStatus,
    RejectReason,
    SubmissionStatus,
    TaskKind,
    TopicSource,
)
from .errors import FolderError  # noqa: F401
from .services.access import (  # noqa: F401
    can_manage_folder,
    can_review_assignment,
    can_view_folder,
    can_view_material,
    can_view_submission,
    can_view_task,
    is_folder_student,
)
from .services.assignments import (  # noqa: F401
    assign_folder,
    assignable_offerings,
    clear_deadline,
    set_deadline,
    set_deadline_for_all,
    unassign,
    window_state,
)
from .services.folders import clone_folder, create_folder  # noqa: F401
from .services.folders import resync as resync_folder  # noqa: F401
from .services.folders import set_folder_status, update_folder
from .services.journal import retry_pending as retry_journal_sync  # noqa: F401
from .services.journal import sync_submission_to_journal  # noqa: F401
from .services.materials import (  # noqa: F401
    archive_material,
    create_material,
    reorder_materials,
    set_material_published,
    update_material,
)
from .services.plagiarism import dismiss_match, restore_match  # noqa: F401
from .services.queries import (  # noqa: F401
    folder_contents,
    list_folders,
    list_materials,
    list_submissions,
    status_counts,
    submission_detail,
    task_progress,
)
from .services.review import (  # noqa: F401
    accept,
    bulk_review,
    check_homework,
    journal_preview,
    reject,
    reopen,
    return_for_revision,
)
from .services.student_feed import student_folders, student_task_view  # noqa: F401
from .services.submissions import remove_draft_file, save_draft, submit  # noqa: F401
from .services.tasks import (  # noqa: F401
    add_task_attachment,
    archive_task,
    create_homework,
    create_task,
    delete_task,
    remove_task_attachment,
    reorder_tasks,
    set_task_published,
    update_task,
)
from .services.topics import create_topic, delete_topic, reorder_topics, set_topic_hidden, update_topic  # noqa: F401

REJECT_REASONS = RejectReason

__all__ = [
    "JOURNAL_SYNC_TOKENS",
    "REJECT_REASONS",
    "SECTION_REVIEW",
    "SECTION_STUDENT",
    "SECTION_TEACHER",
    "STATUS_TOKENS",
    "CodeLanguage",
    "EventKind",
    "FolderError",
    "FolderStatus",
    "JournalSyncStatus",
    "LatePolicy",
    "MaterialKind",
    "PlagiarismStatus",
    "RejectReason",
    "SubmissionStatus",
    "TaskKind",
    "TopicSource",
    "accept",
    "add_task_attachment",
    "archive_material",
    "archive_task",
    "assign_folder",
    "assignable_offerings",
    "bulk_review",
    "can_manage_folder",
    "can_review_assignment",
    "can_view_folder",
    "can_view_material",
    "can_view_submission",
    "can_view_task",
    "check_homework",
    "clear_deadline",
    "clone_folder",
    "create_folder",
    "create_homework",
    "create_material",
    "create_task",
    "create_topic",
    "delete_task",
    "delete_topic",
    "dismiss_match",
    "folder_contents",
    "is_folder_student",
    "journal_preview",
    "list_folders",
    "list_materials",
    "list_submissions",
    "reject",
    "remove_draft_file",
    "remove_task_attachment",
    "reopen",
    "reorder_materials",
    "reorder_tasks",
    "reorder_topics",
    "restore_match",
    "resync_folder",
    "retry_journal_sync",
    "return_for_revision",
    "save_draft",
    "set_deadline",
    "set_deadline_for_all",
    "set_folder_status",
    "set_material_published",
    "set_task_published",
    "set_topic_hidden",
    "status_counts",
    "student_folders",
    "student_task_view",
    "submission_detail",
    "submit",
    "sync_submission_to_journal",
    "task_progress",
    "unassign",
    "update_folder",
    "update_material",
    "update_task",
    "update_topic",
    "window_state",
]
