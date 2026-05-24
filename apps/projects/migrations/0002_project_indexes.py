"""Add composite indexes to Project and ProjectSubmission (FAZA 7).

Neither model had Meta.indexes. Adds the indexes backing the most common
access patterns:

* Project          -> (course, status, -created_at)  course detail pages
* ProjectSubmission-> (project, status, -submitted_at) teacher review queue
* ProjectSubmission-> (student, -submitted_at)         a student's own work

Index-only migration — safe to apply online.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="project",
            index=models.Index(
                fields=["course", "status", "-created_at"],
                name="project_course_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="projectsubmission",
            index=models.Index(
                fields=["project", "status", "-submitted_at"],
                name="projsub_project_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="projectsubmission",
            index=models.Index(
                fields=["student", "-submitted_at"],
                name="projsub_student_idx",
            ),
        ),
    ]
