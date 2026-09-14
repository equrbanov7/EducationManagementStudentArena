"""Data auditi 2026-09-13 §6.2 (W2 2026-09-14) — `exams_examstudentpin` dublikat indeksi.

`exam_student_pin_idx (exam_id, student_id)` `uniq_exam_student_pin` unikal
indeksi ilə eyni açarda idi. `CONCURRENTLY` → `atomic = False`.
"""

from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("exams", "0066_attempt_open_unique_includes_draft"),
    ]

    operations = [
        RemoveIndexConcurrently(model_name="examstudentpin", name="exam_student_pin_idx"),
    ]
