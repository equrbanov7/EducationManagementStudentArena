"""ExamAttempt uniqueness constraints (audit step 2).

Adds two DB-level guarantees:
  1. At most one ``in_progress`` attempt per (user, exam) — partial unique.
  2. Unique ``attempt_number`` per (user, exam).

Existing duplicates are cleaned up first so the constraints can be applied
on production data:
  - extra ``in_progress`` rows (older ``started_at``) are moved to ``expired``;
  - duplicate ``attempt_number`` rows are renumbered chronologically.
"""

from django.db import migrations, models
from django.db.models import Count
from django.utils import timezone


def _dedupe_attempts(apps, schema_editor):
    ExamAttempt = apps.get_model("exams", "ExamAttempt")
    now = timezone.now()

    # 1) Multiple active attempts per (user, exam): keep the newest one,
    #    expire the older ones (the student continues on the newest attempt).
    dup_active = (
        ExamAttempt.objects.filter(status="in_progress")
        .values("user_id", "exam_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in dup_active:
        stale_attempts = list(
            ExamAttempt.objects.filter(
                user_id=row["user_id"],
                exam_id=row["exam_id"],
                status="in_progress",
            ).order_by("-started_at", "-id")
        )[1:]
        for stale in stale_attempts:
            stale.status = "expired"
            if not stale.finished_at:
                stale.finished_at = now
            stale.save(update_fields=["status", "finished_at"])

    # 2) Duplicate attempt_number per (user, exam): renumber chronologically.
    dup_numbers = (
        ExamAttempt.objects.values("user_id", "exam_id", "attempt_number")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    affected_pairs = {(row["user_id"], row["exam_id"]) for row in dup_numbers}
    for user_id, exam_id in affected_pairs:
        attempts = ExamAttempt.objects.filter(user_id=user_id, exam_id=exam_id).order_by("started_at", "id")
        for index, attempt in enumerate(attempts, start=1):
            if attempt.attempt_number != index:
                attempt.attempt_number = index
                attempt.save(update_fields=["attempt_number"])


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0020_examattempt_marked_question_ids"),
    ]

    operations = [
        migrations.RunPython(_dedupe_attempts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="examattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "in_progress")),
                fields=("user", "exam"),
                name="uniq_active_attempt_per_user_exam",
            ),
        ),
        migrations.AddConstraint(
            model_name="examattempt",
            constraint=models.UniqueConstraint(
                fields=("user", "exam", "attempt_number"),
                name="uniq_attempt_number_per_user_exam",
            ),
        ),
    ]
