"""Add composite indexes to Exam (FAZA 7).

The Exam table previously had no Meta.indexes. Single-column FK indexes
(organization, course, author) exist automatically, but the hottest queries
filter by organization AND a secondary column, then order by -created_at:

* tenant exam lists  -> (organization, is_active, -created_at)
* exam-type filters  -> (organization, exam_type, -created_at)
* course exam lists  -> (course, -created_at)
* teacher "my exams" -> (author, -created_at)

Index-only migration — no schema/field change, safe to apply online.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0008_exam_results_hidden_from_students"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["organization", "is_active", "-created_at"],
                name="exam_org_active_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["organization", "exam_type", "-created_at"],
                name="exam_org_type_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["course", "-created_at"],
                name="exam_course_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["author", "-created_at"],
                name="exam_author_created_idx",
            ),
        ),
    ]
