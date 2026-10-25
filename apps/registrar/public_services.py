"""Registrar public service exports; implementation ownership stays in registrar."""

from . import analytics  # noqa: F401
from . import catalog_console  # noqa: F401
from . import cohort_plans  # noqa: F401 — qrupun öz qəbul ili planı (workload generation, 2026-10-19)
from . import course_groups  # noqa: F401
from . import credit_recognition_read  # noqa: F401 — «Xarici nəticənin tanınması»: açar + əhatə (2026-10-25)
from . import credit_source  # noqa: F401 — tələbənin fənn krediti: plan (fənn + semestr) → kataloq (R01, 2026-10-21)
from . import dashboard_data  # noqa: F401
from . import entry_standard  # noqa: F401
from . import gradebook  # noqa: F401
from . import grading_scale  # noqa: F401
from . import handover  # noqa: F401
from . import handover_actions  # noqa: F401
from . import handover_query  # noqa: F401
from . import interim_assessment  # noqa: F401
from . import journal_close  # noqa: F401
from . import journal_hygiene  # noqa: F401
from . import journal_hygiene_actions  # noqa: F401
from . import journal_hygiene_rows  # noqa: F401
from . import journal_scope  # noqa: F401
from . import kollokvium_notifications  # noqa: F401
from . import kollokvium_windows  # noqa: F401
from . import legacy_grade_review  # noqa: F401
from . import legacy_grade_review_actions  # noqa: F401
from . import legacy_grade_review_counts  # noqa: F401
from . import legacy_grade_review_rows  # noqa: F401
from . import lessons_log  # noqa: F401
from . import movements  # noqa: F401
from . import retake_access  # noqa: F401 — 25% / alt qrup müraciəti: açar + əhatə (2026-10-18)
from . import retake_chance  # noqa: F401 — «İmtahan şansı ver» rəsmi qeydi (2026-10-18)
from . import retake_fees  # noqa: F401 — 25% təxmini məbləği + təhsil haqqı cədvəli (2026-10-19)
from . import retake_window  # noqa: F401 — 25% müraciət pəncərəsi (İmtahan mərkəzi, 2026-10-19)
from . import schedule  # noqa: F401
from . import schedule_conflicts  # noqa: F401
from . import schedule_docx_match  # noqa: F401 — cədvəl → tapşırıq sətri (workload, 2026-10-15)
from . import schedule_docx_parse  # noqa: F401
from . import schedule_editor  # noqa: F401
from . import schedule_editor_actions  # noqa: F401
from . import schedule_grid  # noqa: F401
from . import schedule_manage  # noqa: F401
from . import schedule_manage_actions  # noqa: F401
from . import schedule_publish  # noqa: F401
from . import schedule_rooms  # noqa: F401 — dialoqun «Korpus → Otaq» kataloqu (2026-10-17)
from . import schedule_suggest  # noqa: F401 — «Uyğun vaxtlar» + otaq tövsiyəsi (2026-10-17)
from . import selfwork_points  # noqa: F401
from . import services  # noqa: F401
from . import status  # noqa: F401
from . import student_group_names  # noqa: F401 — tələbənin cari reyestr qrupunun adı (süzgəclər, 2026-10-25)
from . import subgroup_rollup  # noqa: F401
from . import transcript  # noqa: F401
from . import transfer  # noqa: F401
from . import exam_eligibility as eligibility_rules  # noqa: F401
from .attendance import DEFAULT_ABSENCE_LIMIT_PERCENT  # noqa: F401
from .attendance import attendance_score  # noqa: F401
from .cabinet_policy import transcript_policy  # noqa: F401
from .catalog_registry import build_programs_registry  # noqa: F401
from .catalog_registry import build_subject_catalog  # noqa: F401
from .corrections import CORRECT_PERMISSION  # noqa: F401
from .corrections import apply_correction  # noqa: F401
from .curriculum_registry import build_curriculum_editor  # noqa: F401
from .gradebook import recompute_absence_hours  # noqa: F401
from .grading_scale import bands_text  # noqa: F401
from .grading_scale import is_custom  # noqa: F401
from .handover_actions import REVERT_BLOCKER_CODES  # noqa: F401
from .movements import RULES  # noqa: F401
from .page_contexts import _season_label as season_label  # noqa: F401
from .plan_hours import plan_hours_for_offering  # noqa: F401
from .plan_hours import program_for_offering  # noqa: F401
from .plan_hours import workload_hours_for_offering  # noqa: F401
from .semester_open import build_semester_opening  # noqa: F401
from .semester_open import offering_counts_by_chair  # noqa: F401
from .syllabus_pdf import render_syllabus_pdf  # noqa: F401
from .syllabus_reuse_targets import instructor_offering  # noqa: F401
from .syllabus_reuse_targets import instructor_offerings  # noqa: F401
from .syllabus_reuse_targets import plan_hours_by_offering  # noqa: F401
from .syllabus_reuse_targets import programs_by_offering  # noqa: F401
from .teaching_activity import instructor_activity  # noqa: F401 — «Kadr analitikası» (2026-10-11)

__all__ = [
    "CORRECT_PERMISSION",
    "DEFAULT_ABSENCE_LIMIT_PERCENT",
    "REVERT_BLOCKER_CODES",
    "RULES",
    "analytics",
    "apply_correction",
    "attendance_score",
    "bands_text",
    "build_curriculum_editor",
    "build_programs_registry",
    "build_semester_opening",
    "build_subject_catalog",
    "catalog_console",
    "course_groups",
    "credit_source",
    "dashboard_data",
    "eligibility_rules",
    "entry_standard",
    "gradebook",
    "grading_scale",
    "handover",
    "handover_actions",
    "handover_query",
    "instructor_activity",
    "instructor_offering",
    "instructor_offerings",
    "interim_assessment",
    "is_custom",
    "journal_close",
    "journal_hygiene",
    "journal_hygiene_actions",
    "journal_hygiene_rows",
    "journal_scope",
    "kollokvium_notifications",
    "kollokvium_windows",
    "legacy_grade_review",
    "legacy_grade_review_actions",
    "legacy_grade_review_counts",
    "legacy_grade_review_rows",
    "lessons_log",
    "movements",
    "offering_counts_by_chair",
    "plan_hours_by_offering",
    "plan_hours_for_offering",
    "cohort_plans",
    "programs_by_offering",
    "workload_hours_for_offering",
    "program_for_offering",
    "recompute_absence_hours",
    "render_syllabus_pdf",
    "retake_access",
    "credit_recognition_read",
    "retake_chance",
    "retake_fees",
    "retake_window",
    "schedule",
    "schedule_conflicts",
    "schedule_docx_match",
    "schedule_docx_parse",
    "schedule_editor",
    "schedule_editor_actions",
    "schedule_grid",
    "schedule_manage",
    "schedule_manage_actions",
    "schedule_publish",
    "schedule_rooms",
    "schedule_suggest",
    "season_label",
    "selfwork_points",
    "services",
    "status",
    "student_group_names",
    "subgroup_rollup",
    "transcript",
    "transcript_policy",
    "transfer",
]
