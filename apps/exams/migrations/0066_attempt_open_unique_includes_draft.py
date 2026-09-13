"""Audit 2026-09-13 EX-08 (P2): açıq cəhd unikallığı «draft» statusunu da əhatə edir.

`uniq_active_attempt_per_user_exam` yalnız `in_progress` üçün idi; tələbə
`save_draft` ilə cəhdi `draft`-a salandan sonra DB ikinci açıq cəhdi
bloklamırdı. Tətbiq qatı (`get_active_attempt_for_user`) hər iki statusu
«açıq» sayır — constraint ona bərabərləşdirilir. Əvvəlcə mövcud dublikatlar
(eyni user+exam üçün birdən çox draft/in_progress) ən yenisi saxlanmaqla
`expired` edilir ki, constraint yaradıla bilsin (0021-dəki naxış).
"""

from django.db import migrations, models


def _dedupe_open_attempts(apps, schema_editor):
    ExamAttempt = apps.get_model("exams", "ExamAttempt")
    seen = set()
    open_attempts = ExamAttempt.objects.filter(status__in=("draft", "in_progress")).order_by(
        "user_id", "exam_id", "-started_at", "-id"
    )
    for attempt in open_attempts.iterator():
        key = (attempt.user_id, attempt.exam_id)
        if key in seen:
            attempt.status = "expired"
            attempt.save(update_fields=["status"])
            continue
        seen.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0065_question_submission_event_append_only"),
    ]

    operations = [
        migrations.RunPython(_dedupe_open_attempts, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="examattempt",
            name="uniq_active_attempt_per_user_exam",
        ),
        migrations.AddConstraint(
            model_name="examattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ("draft", "in_progress"))),
                fields=("user", "exam"),
                name="uniq_active_attempt_per_user_exam",
            ),
        ),
    ]
