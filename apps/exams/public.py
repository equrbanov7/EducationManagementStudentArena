"""exams modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

Digər modullar imtahan datası/xidmətləri üçün YALNIZ bu fasadı istifadə
etməlidir (AGENTS §5). Genişlənmə nöqtəsi: apps.exams.score_adjustments
(bal düzəlişləri — appeals ready()-də qeydiyyat). Modellərə (Exam,
ExamAttempt, StudentGroup...) ehtiyac olduqda ORM əlaqələri və ya
django_apps.get_model istifadə edin.
"""

from apps.exams.constants import (  # noqa: F401
    ATTEMPT_FINISHED_STATUSES,
    DEFAULT_EXAM_LANGUAGE,
    EXAM_LANGUAGE_CHOICES,
    get_live_active_states,
    get_live_session_model,
)
from apps.exams.domain.ai_config import (  # noqa: F401
    get_ai_config,
)
from apps.exams.domain.final_center import (  # noqa: F401
    ExamRoom,
    ExamRoomComputer,
)
from apps.exams.features import (  # noqa: F401
    without_disabled_practical_exams,
)
from apps.exams.forms import (  # noqa: F401
    StudentGroupForm,
)
from apps.exams.services.access_policy import (  # noqa: F401
    can_assign_invigilators,
    can_create_question_bank,
    can_manage_exam_questions,
    can_manage_exam_rooms,
    can_manage_final_exam_content,
    ensure_can_manage_exam_rooms,
    is_exam_center_user,
    is_teacher_user,
)
from apps.exams.services.ai_summary import _get_rate_limit as get_ai_rate_limit  # noqa: F401
from apps.exams.services.ai_summary import (  # noqa: F401
    generate_exam_statistics_summary,
)
from apps.exams.services.final_center import (  # noqa: F401
    RoomAdminError,
    add_computer,
    bulk_add_computers,
    student_final_exam_context,
    update_computer,
    user_supervises_final_sessions,
)
from apps.exams.services.grading import (  # noqa: F401
    calculate_attempt_score,
)
from apps.exams.services.language_variants import (  # noqa: F401
    available_language_options,
)
from apps.exams.services.question_bank_attach import (  # noqa: F401
    accessible_banks,
)
from apps.exams.services.result_calculation import (  # noqa: F401
    calculate_test_attempt_result,
)
from apps.exams.services.result_release import (  # noqa: F401
    exam_answers_release_locked,
)
from apps.exams.services.review_visibility import (  # noqa: F401
    resolve_exam_attempt_name_visibility,
    resolve_exam_attempt_review_window_seconds,
)
from apps.exams.services.supervision import attach_attempt_interventions  # noqa: F401
from apps.exams.services.teacher_dashboard import (  # noqa: F401
    build_teacher_exam_dashboard,
)
from apps.exams.views.shared.tenant import (  # noqa: F401
    tenant_scoped_exams,
)

__all__ = [
    "ATTEMPT_FINISHED_STATUSES",
    "DEFAULT_EXAM_LANGUAGE",
    "ExamRoom",
    "ExamRoomComputer",
    "RoomAdminError",
    "StudentGroupForm",
    "add_computer",
    "bulk_add_computers",
    "can_assign_invigilators",
    "update_computer",
    "get_ai_rate_limit",
    "EXAM_LANGUAGE_CHOICES",
    "accessible_banks",
    "available_language_options",
    "attach_attempt_interventions",
    "build_teacher_exam_dashboard",
    "calculate_attempt_score",
    "can_create_question_bank",
    "can_manage_exam_questions",
    "can_manage_exam_rooms",
    "can_manage_final_exam_content",
    "ensure_can_manage_exam_rooms",
    "exam_answers_release_locked",
    "is_exam_center_user",
    "calculate_test_attempt_result",
    "generate_exam_statistics_summary",
    "get_ai_config",
    "get_live_active_states",
    "get_live_session_model",
    "is_teacher_user",
    "resolve_exam_attempt_name_visibility",
    "resolve_exam_attempt_review_window_seconds",
    "student_final_exam_context",
    "tenant_scoped_exams",
    "user_supervises_final_sessions",
    "without_disabled_practical_exams",
]
