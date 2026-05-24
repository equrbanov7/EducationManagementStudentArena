"""Add a composite index to LabSubmission (FAZA 7).

LabSubmission had no Meta.indexes. The teacher grading queue filters a lab
assignment's submissions by status, newest-first:

* LabSubmission -> (assignment, status, -submitted_at)

Index-only migration — safe to apply online.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labs", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="labsubmission",
            index=models.Index(
                fields=["assignment", "status", "-submitted_at"],
                name="labsub_assign_status_idx",
            ),
        ),
    ]
