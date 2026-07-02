"""notifications modulunun PUBLIC API fasadı (M2, 2026-07-02).

Digər modullar bildiriş göndərmək/oxumaq üçün YALNIZ bu fasadı istifadə
etməlidir (birbaşa models/servis-daxili importlar əvəzinə) — bax AGENTS §5.
Mövcud `apps.notifications.services` çağırışları işlək qalır; yeni kod üçün
kanonik giriş nöqtəsi budur. Modullar üzrə public.py pattern-inin İLK nümunəsi.
"""

from apps.notifications.services import (  # noqa: F401
    create_notification,
    get_exam_assigned_user_ids,
    get_unread_count,
    notify_student_about_feedback,
    notify_task_assignment,
    notify_teacher_about_submission,
)

__all__ = [
    "create_notification",
    "notify_task_assignment",
    "notify_teacher_about_submission",
    "notify_student_about_feedback",
    "get_exam_assigned_user_ids",
    "get_unread_count",
]
