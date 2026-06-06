import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

APPEAL_STATUS_CHOICES = [
    ("pending", "pending"),
    ("under_review", "under_review"),
    ("accepted", "accepted"),
    ("rejected", "rejected"),
    ("partially_accepted", "partially_accepted"),
]

APPEAL_ITEM_STATUS_CHOICES = [
    ("pending", "pending"),
    ("accepted", "accepted"),
    ("rejected", "rejected"),
]

APPEAL_TYPE_CHOICES = [
    ("wrong_question", "wrong_question"),
    ("wrong_answer_key", "wrong_answer_key"),
    ("unclear_question", "unclear_question"),
    ("out_of_syllabus", "out_of_syllabus"),
    ("technical_issue", "technical_issue"),
    ("grading_issue", "grading_issue"),
    ("other", "other"),
]


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("exams", "0017_question_bank_library"),
        ("organizations", "0006_migrate_legacy_permission_aliases"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Appeal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=APPEAL_STATUS_CHOICES,
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="reviewed_at")),
                ("reviewer_note", models.TextField(blank=True, verbose_name="reviewer_note")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appeals",
                        to="exams.examattempt",
                        verbose_name="attempt",
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appeals",
                        to="exams.exam",
                        verbose_name="exam",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exam_appeals",
                        to="organizations.organization",
                        verbose_name="organization",
                    ),
                ),
                (
                    "org_unit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="exam_appeals",
                        to="organizations.orgunit",
                        verbose_name="org_unit",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_appeals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="reviewed_by",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exam_appeals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="student",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
                "ordering": ["-created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="AppealItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("appeal_type", models.CharField(choices=APPEAL_TYPE_CHOICES, max_length=30, verbose_name="appeal_type")),
                ("comment", models.TextField(verbose_name="comment")),
                (
                    "status",
                    models.CharField(
                        choices=APPEAL_ITEM_STATUS_CHOICES,
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("reviewer_response", models.TextField(blank=True, verbose_name="reviewer_response")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="resolved_at")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "appeal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="appeals.appeal",
                        verbose_name="appeal",
                    ),
                ),
                (
                    "answer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="appeal_items",
                        to="exams.examanswer",
                        verbose_name="answer",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appeal_items",
                        to="exams.examquestion",
                        verbose_name="question",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_appeal_items",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="resolved_by",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="ScoreAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "delta_points",
                    models.DecimalField(decimal_places=2, default=0, max_digits=7, verbose_name="delta_points"),
                ),
                ("previous_is_correct", models.BooleanField(blank=True, null=True)),
                ("new_is_correct", models.BooleanField(blank=True, null=True)),
                ("previous_score", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("new_score", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("reverted", models.BooleanField(default=False)),
                (
                    "appeal_item",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="score_adjustment",
                        to="appeals.appealitem",
                        verbose_name="appeal_item",
                    ),
                ),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="score_adjustments",
                        to="exams.examattempt",
                        verbose_name="attempt",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="score_adjustments",
                        to="exams.examquestion",
                        verbose_name="question",
                    ),
                ),
                (
                    "applied_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="applied_score_adjustments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="applied_by",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
                "ordering": ["-applied_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="appeal",
            index=models.Index(fields=["organization", "status", "-created_at"], name="appeal_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="appeal",
            index=models.Index(fields=["exam", "status"], name="appeal_exam_status_idx"),
        ),
        migrations.AddIndex(
            model_name="appeal",
            index=models.Index(fields=["student", "-created_at"], name="appeal_student_created_idx"),
        ),
        migrations.AddIndex(
            model_name="appealitem",
            index=models.Index(fields=["appeal", "status"], name="appeal_item_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="appealitem",
            constraint=models.UniqueConstraint(fields=("appeal", "question"), name="appeal_item_unique_question"),
        ),
        migrations.AddIndex(
            model_name="scoreadjustment",
            index=models.Index(fields=["attempt"], name="score_adj_attempt_idx"),
        ),
    ]
