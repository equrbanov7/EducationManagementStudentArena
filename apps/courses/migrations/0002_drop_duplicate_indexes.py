"""Data auditi 2026-09-13 §6.2 (W2 2026-09-14) — `courses_*` dublikat indeksləri.

* `courses_course.slug` — `unique=True` indeksi (`courses_course_slug_key`) var;
* `courses_coursegroup.course_id` / `instructor_id` — FK avtomatik indeksləri var;
* `courses_coursetopic (course_id, order)` — `unique_together` indeksi var.

Dördü də `Meta.indexes`-də eyni açarın təkrarı idi. `CONCURRENTLY` → `atomic = False`.
"""

from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("courses", "0001_initial"),
    ]

    operations = [
        RemoveIndexConcurrently(model_name="course", name="courses_cou_slug_2e551f_idx"),
        RemoveIndexConcurrently(model_name="coursegroup", name="courses_cou_course__225864_idx"),
        RemoveIndexConcurrently(model_name="coursegroup", name="courses_cou_instruc_f2ed74_idx"),
        RemoveIndexConcurrently(model_name="coursetopic", name="courses_cou_course__0e20e3_idx"),
    ]
