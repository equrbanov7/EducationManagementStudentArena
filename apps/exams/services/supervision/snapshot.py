"""supervision paketi — snapshot."""

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import SupervisionIncident
from apps.exams.services.randomizer import build_shuffled_options

from .monitor import (
    get_exam_question_total,
)


def _media_url(file_field):
    """Safely return a media file's URL, or None when absent/unset."""
    try:
        if file_field and getattr(file_field, "name", ""):
            return file_field.url
    except Exception:
        pass
    return None


def _question_kind(question, exam_type):
    """
    Coarse per-question kind for the monitor modal badge.

    ``ExamQuestion`` has no ``question_type`` column, so we infer the kind from
    the exam type and the question's own paint/option configuration:
      - "test"    → has selectable options (single/multiple choice)
      - "written" → free-text / open answer
      - "paint"   → drawing-enabled question
      - "coding"  → practical coding question
    """
    if exam_type == "coding":
        return "coding"
    if getattr(question, "paint_enabled_effective", False):
        return "paint"
    if exam_type == "test":
        return "test"
    # For written/mixed exams, a question with options behaves like a test item;
    # otherwise it is a free-text written answer.
    has_options = False
    try:
        has_options = question.options.exists()
    except Exception:
        has_options = False
    return "test" if has_options else "written"


def _written_test_snapshot_answers(attempt, exam_type):
    """
    Build per-question answer rows for test / written exams.

    Walks the answers that were created for this attempt, in creation order.
    That creation order is the student's assigned question sequence; it may be
    different from the exam bank order when random question distribution is on.
    Correct/selected-option flags are included because this view is teacher-only.

    Returns ``(rows, answered_count)``.
    """
    answers = list(
        attempt.answers.select_related("question", "question__exam", "question__block")
        .prefetch_related("question__options", "selected_options", "files")
        .order_by("id")
    )

    rows = []
    answered_count = 0
    for ans in answers:
        q = ans.question
        kind = _question_kind(q, exam_type)

        selected = []
        all_options = []
        text_answer = ""
        has_paint = False
        files = []

        selected_options = list(ans.selected_options.all())
        selected_option_ids = {opt.id for opt in selected_options}
        if kind == "test":
            option_by_id = {opt.id: opt for opt in q.options.all()}
            option_rows = build_shuffled_options(attempt.id, q)
            for option_row in option_rows:
                opt = option_by_id.get(option_row["id"])
                if opt is None:
                    continue
                packed = {
                    "id": opt.id,
                    "text": option_row["text"],
                    "label": option_row["label"],
                    "is_correct": opt.is_correct,
                    "is_selected": opt.id in selected_option_ids,
                }
                all_options.append(packed)
                if packed["is_selected"]:
                    selected.append(
                        {
                            "id": packed["id"],
                            "text": packed["text"],
                            "label": packed["label"],
                            "is_correct": packed["is_correct"],
                        }
                    )
        else:
            selected = [
                {"id": opt.id, "text": opt.text, "label": opt.label, "is_correct": opt.is_correct}
                for opt in selected_options
            ]

        text_answer = (ans.text_answer or "")[:4000]
        has_paint = bool(getattr(ans, "has_paint", False))
        files = [f.filename() for f in ans.files.all()]
        is_answered = bool(selected or text_answer.strip() or has_paint or files)
        if is_answered:
            answered_count += 1

        # The set of correct option texts lets the teacher see at a glance what
        # the right answer was for a test item.
        correct_options = [
            {"id": opt["id"], "text": opt["text"], "label": opt["label"]} for opt in all_options if opt["is_correct"]
        ]

        rows.append(
            {
                "kind": kind,
                "question_text": (q.text or "")[:600],
                "image_url": _media_url(getattr(q, "image", None)),
                "video_url": _media_url(getattr(q, "video", None)),
                "options": all_options,
                "selected_options": selected,
                "correct_options": correct_options,
                "text_answer": text_answer,
                "has_paint": has_paint,
                "paint_image_url": _media_url(getattr(ans, "paint_image", None)),
                "files": files,
                "is_correct": bool(ans.is_correct),
                "is_answered": is_answered,
                "updated_at": ans.updated_at.isoformat() if ans.updated_at else None,
            }
        )

    return rows, answered_count


def _coding_snapshot_answers(attempt):
    """
    Build per-question answer rows for a practical / coding exam.

    Reads the latest saved CodingSubmission for each coding question on the
    exam (draft autosaves while in progress, or the final submission once the
    student submits) and surfaces every file with its full content so the
    teacher can read exactly what the student is typing, file by file.

    Returns ``(rows, answered_count)``.
    """
    from apps.exams.models import CodingExamQuestion, CodingSubmission

    coding_questions = (
        CodingExamQuestion.objects.filter(question__exam=attempt.exam, question__is_active=True)
        .select_related("question")
        .order_by("question__order", "id")
    )

    # Latest submission per coding question for this attempt. ``-is_final`` then
    # ``-submitted_at`` keeps the final submission ahead of older drafts, and the
    # newest draft otherwise. code_files prefetched to avoid an N+1.
    submissions = (
        CodingSubmission.objects.filter(attempt=attempt)
        .select_related("question")
        .prefetch_related("code_files")
        .order_by("-is_final", "-submitted_at")
    )
    latest_by_question = {}
    for sub in submissions:
        latest_by_question.setdefault(sub.question_id, sub)

    rows = []
    answered_count = 0
    for cq in coding_questions:
        sub = latest_by_question.get(cq.id)
        files = []
        if sub is not None:
            files = [
                {"name": item["name"], "content": (item["content"] or "")[:20000]}
                for item in _submission_file_items_safe(sub)
            ]
        # Drop files that are entirely empty so an untouched starter file does
        # not read as "answered".
        non_empty = [f for f in files if (f["content"] or "").strip()]
        is_answered = bool(non_empty)
        if is_answered:
            answered_count += 1

        rows.append(
            {
                "kind": "coding",
                "question_text": (cq.title or cq.problem_statement or "")[:600],
                "image_url": _media_url(getattr(cq.question, "image", None)),
                "video_url": _media_url(getattr(cq.question, "video", None)),
                "language": cq.language,
                "files": files,
                "execution_status": getattr(sub, "execution_status", "") if sub else "",
                "output": (getattr(sub, "output", "") or "")[:4000] if sub else "",
                "is_answered": is_answered,
                "updated_at": sub.updated_at.isoformat() if (sub and sub.updated_at) else None,
            }
        )

    return rows, answered_count


def _submission_file_items_safe(submission):
    """
    Files for a coding submission as ``[{name, content}, ...]``.

    Prefers the structured CodingFile rows; falls back to the JSON ``files``
    list stored on the submission (the shape coding_autosave writes). Mirrors
    the student-side ``_submission_file_items`` helper so monitor and student
    views never disagree about what was saved.
    """
    code_files = list(submission.code_files.all())
    if code_files:
        return [{"name": cf.name, "content": cf.content or ""} for cf in code_files]
    return [
        {"name": item.get("name") or "file.txt", "content": item.get("content") or ""}
        for item in (submission.files or [])
        if isinstance(item, dict)
    ]


def get_attempt_live_snapshot(attempt):
    """
    Detailed live snapshot of a single student's in-progress (or finished)
    attempt — what they have answered so far and every supervision event.

    This is read-only monitoring: it never mutates the attempt, so a teacher can
    "look over the shoulder" without blocking the student. Scope MUST be enforced
    by the caller (exam already tenant/permission scoped).
    """
    if not exam_supervision_enabled():
        return {
            "attempt_id": attempt.id,
            "student_name": attempt.user.get_full_name() or attempt.user.username,
            "student_username": attempt.user.username,
            "supervision_status": "active",
            "manual_lock": False,
            "violation_count": 0,
            "answered": 0,
            "total_questions": get_exam_question_total(attempt.exam),
            "correct_count": attempt.correct_count,
            "wrong_count": attempt.wrong_count,
            "score_percent": None,
            "checked_by_teacher": attempt.checked_by_teacher,
            "teacher_score": attempt.teacher_score,
            "is_finished": attempt.is_finished,
            "status": attempt.status,
            "exam_title": attempt.exam.title,
            "exam_type": getattr(attempt.exam, "exam_type", "") or "",
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
            "answers": [],
            "incidents": [],
        }

    exam_type = getattr(attempt.exam, "exam_type", "") or ""
    if exam_type == "coding":
        # Practical / coding exams store the student's work in CodingSubmission
        # (one per coding question), NOT in attempt.answers.  We surface the
        # latest saved files per question so the teacher sees exactly what the
        # student has typed live, file by file.
        answer_rows, answered_count = _coding_snapshot_answers(attempt)
        total_questions = len(answer_rows) or get_exam_question_total(attempt.exam)
    else:
        # Test / written exams keep their live answers in attempt.answers,
        # autosaved per question while the student works.
        answer_rows, answered_count = _written_test_snapshot_answers(attempt, exam_type)
        total_questions = len(answer_rows) or get_exam_question_total(attempt.exam)

    incidents = SupervisionIncident.objects.filter(attempt=attempt).order_by("-timestamp")[:50]
    incident_rows = [
        {
            "event_type": inc.event_type,
            "event_display": inc.get_event_type_display(),
            "severity": inc.severity,
            "timestamp": inc.timestamp.isoformat(),
            "violation_count_at_time": inc.violation_count_at_time,
        }
        for inc in incidents
    ]

    # Precise score for a single attempt — safe to compute here (one attempt,
    # not the whole list). Only surfaced once the attempt is finished.
    score_percent = None
    if attempt.is_finished:
        try:
            score_percent = round(float(attempt.score_percent), 1)
        except Exception:
            graded = attempt.correct_count + attempt.wrong_count
            score_percent = round(attempt.correct_count * 100 / graded, 1) if graded else None

    return {
        "attempt_id": attempt.id,
        "student_name": attempt.user.get_full_name() or attempt.user.username,
        "student_username": attempt.user.username,
        "supervision_status": attempt.supervision_status,
        "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
        "violation_count": attempt.supervision_violation_count,
        "answered": answered_count,
        "total_questions": total_questions,
        "correct_count": attempt.correct_count,
        "wrong_count": attempt.wrong_count,
        "score_percent": score_percent,
        "checked_by_teacher": attempt.checked_by_teacher,
        "teacher_score": attempt.teacher_score,
        "is_finished": attempt.is_finished,
        "status": attempt.status,
        "exam_title": attempt.exam.title,
        "exam_type": getattr(attempt.exam, "exam_type", "") or "",
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "answers": answer_rows,
        "incidents": incident_rows,
    }
