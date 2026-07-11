from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone


def merge_submission_content(submission_text="", submission_url=""):
    parts = []
    if submission_text:
        parts.append(str(submission_text).strip())
    if submission_url:
        parts.append(str(submission_url).strip())
    return "\n".join(part for part in parts if part)


def attach_submission_file(submission, uploaded_file, *, original_name=""):
    attach_method = getattr(submission, "attach_uploaded_file", None)
    if callable(attach_method):
        attach_method(uploaded_file, original_name=original_name)
        return "files"

    submission.file = uploaded_file
    return "file"


@transaction.atomic
def create_submission(
    *,
    submission_model,
    task_field_name,
    task,
    student_field_name,
    student,
    submitted_status,
    submission_file=None,
    submission_text="",
    submission_url="",
    original_file_name="",
    extra_create_fields=None,
):
    payload = {
        task_field_name: task,
        student_field_name: student,
        "content": merge_submission_content(submission_text, submission_url),
        "status": submitted_status,
    }
    if extra_create_fields:
        payload.update(extra_create_fields)

    submission = submission_model.objects.create(**payload)

    if submission_file:
        file_update_field = attach_submission_file(
            submission,
            submission_file,
            original_name=original_file_name,
        )
        submission.save(update_fields=[file_update_field])

    return submission


@transaction.atomic
def update_submission(
    submission,
    *,
    submitted_status,
    submission_file=None,
    submission_text=None,
    submission_url=None,
    original_file_name="",
):
    update_fields = ["submitted_at", "status"]

    if submission_file is not None:
        update_fields.append(
            attach_submission_file(
                submission,
                submission_file,
                original_name=original_file_name,
            )
        )

    if submission_text is not None:
        submission.content = merge_submission_content(submission_text, submission_url or "")
        update_fields.append("content")
    elif submission_url is not None:
        submission.content = merge_submission_content(submission.content, submission_url)
        update_fields.append("content")

    submission.submitted_at = timezone.now()
    submission.status = submitted_status
    submission.save(update_fields=update_fields)

    return submission


def _resolve_task_max_score(submission):
    """Submission-un aid olduğu tapşırığın max balını tap (assignment/project/lab).

    Tapılmasa None qaytarır (clamp tətbiq olunmur — geriyə-uyğunluq).
    """
    for attr in ("assignment", "project"):
        task = getattr(submission, attr, None)
        if task is not None:
            # LabSubmission.assignment → LabAssignment.lab.max_score
            max_score = getattr(task, "max_score", None)
            if max_score is None:
                lab = getattr(task, "lab", None)
                max_score = getattr(lab, "max_score", None)
            if max_score is not None:
                return max_score
    return None


def _clamp_score(parsed_score, max_score):
    """Balı [0, max] aralığına salır (audit: grade clamp invariantı)."""
    if parsed_score is None:
        return parsed_score
    try:
        value = Decimal(str(parsed_score))
    except (InvalidOperation, ValueError, TypeError):
        return parsed_score
    if value < 0:
        value = Decimal("0")
    if max_score is not None:
        try:
            ceiling = Decimal(str(max_score))
            if value > ceiling:
                value = ceiling
        except (InvalidOperation, ValueError, TypeError):
            pass
    return value


@transaction.atomic
def apply_grade(submission, score, feedback, graded_by, *, graded_status="graded", preserve_existing_graded_at=False):
    parsed_score = parse_score_value(score, default=score)
    # Audit: qiymət heç vaxt [0, max] aralığından kənara çıxmamalıdır.
    parsed_score = _clamp_score(parsed_score, _resolve_task_max_score(submission))

    submission.grade = parsed_score
    submission.feedback = feedback
    submission.graded_by = graded_by
    submission.status = graded_status

    update_fields = ["grade", "feedback", "graded_by", "status"]
    if not preserve_existing_graded_at or not submission.graded_at:
        submission.graded_at = timezone.now()
        update_fields.append("graded_at")

    submission.save(update_fields=update_fields)
    return submission


def bulk_grade_submissions(submissions, scores, feedback_list, graded_by, *, graded_status="graded"):
    # Audit: `submissions` unordered queryset ola bilər — score/feedback
    # siyahıları POZİSİYA ilə uyğunlaşdırılır. Materialize edib zip etməklə
    # balın yanlış tələbəyə getmə riski var idi. İndi çağıran tərəf sıralı
    # cütlük ötürməlidir; uzunluq uyğunsuzluğu transaction açılmadan bloklanır.
    submissions = list(submissions)
    if not (len(submissions) == len(scores) == len(feedback_list)):
        raise ValueError("submissions, scores və feedback_list eyni uzunluqda olmalıdır")
    return _bulk_grade_submissions_atomic(submissions, scores, feedback_list, graded_by, graded_status=graded_status)


@transaction.atomic
def _bulk_grade_submissions_atomic(submissions, scores, feedback_list, graded_by, *, graded_status="graded"):
    count = 0
    for submission, score, feedback in zip(submissions, scores, feedback_list):
        apply_grade(submission, score, feedback, graded_by, graded_status=graded_status)
        count += 1
    return count


@transaction.atomic
def assign_task_to_students(task, student_ids):
    users = task.assigned_students.model.objects.filter(id__in=student_ids)
    count = 0

    for user in users:
        if not task.assigned_students.filter(id=user.id).exists():
            task.assigned_students.add(user)
            count += 1

    return count


@transaction.atomic
def assign_task_to_group(task, student_group):
    count = 0

    for student in student_group.students.all():
        if not task.assigned_students.filter(id=student.id).exists():
            task.assigned_students.add(student)
            count += 1

    return count


def get_task_submissions(*, submission_model, task_field_name, task, student_field_name, status=None, group_name=None):
    qs = submission_model.objects.filter(**{task_field_name: task}).select_related(
        student_field_name,
        f"{student_field_name}__profile",
        "graded_by",
    )

    if status:
        qs = qs.filter(status=status)

    if group_name:
        from apps.courses.models import CourseMembership

        student_ids = CourseMembership.objects.filter(
            course=task.course,
            role="student",
            group_name=group_name,
        ).values_list("user_id", flat=True)
        qs = qs.filter(**{f"{student_field_name}_id__in": student_ids})

    return qs.order_by("-submitted_at")


def get_pending_task_submissions(
    *,
    submission_model,
    task_field_name,
    student_field_name,
    teacher_lookup,
    teacher,
    pending_status,
    organization=None,
):
    qs = submission_model.objects.filter(
        **{
            teacher_lookup: teacher,
            "status": pending_status,
        }
    ).select_related(task_field_name, student_field_name)

    if organization is not None:
        qs = qs.filter(**{f"{task_field_name}__course__organization": organization})

    return qs.order_by("submitted_at")


def parse_score_value(value, *, default=None):
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return default
