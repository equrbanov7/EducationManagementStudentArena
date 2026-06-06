import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.exams.models

EXAM_LANGUAGE_CHOICES = [
    ("az", "Azərbaycan dili"),
    ("en", "English"),
    ("ru", "Русский"),
    ("tr", "Türkçe"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0016_backfill_language_variants"),
        ("organizations", "0006_migrate_legacy_permission_aliases"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="questionbank",
            name="topic",
            field=models.CharField(blank=True, help_text="topic", max_length=150, verbose_name="topic"),
        ),
        migrations.AddField(
            model_name="questionbank",
            name="language",
            field=models.CharField(
                choices=EXAM_LANGUAGE_CHOICES,
                db_index=True,
                default="az",
                help_text="language",
                max_length=10,
                verbose_name="language",
            ),
        ),
        migrations.AddField(
            model_name="questionbank",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="question_banks",
                to="organizations.organization",
                verbose_name="organization",
            ),
        ),
        migrations.AddField(
            model_name="questionbank",
            name="org_unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="question_banks",
                to="organizations.orgunit",
                verbose_name="org_unit",
            ),
        ),
        migrations.CreateModel(
            name="BankQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(verbose_name="text")),
                (
                    "question_type",
                    models.CharField(
                        choices=[("test", "test"), ("written", "written")],
                        default="test",
                        max_length=20,
                        verbose_name="question_type",
                    ),
                ),
                (
                    "answer_mode",
                    models.CharField(
                        choices=[("single", "single"), ("multiple", "multiple")],
                        default="single",
                        max_length=20,
                        verbose_name="answer_mode",
                    ),
                ),
                ("correct_answer", models.TextField(blank=True, verbose_name="correct_answer")),
                (
                    "difficulty",
                    models.CharField(
                        choices=[("easy", "easy"), ("medium", "medium"), ("hard", "hard")],
                        default="medium",
                        max_length=20,
                        verbose_name="difficulty",
                    ),
                ),
                (
                    "language",
                    models.CharField(
                        choices=EXAM_LANGUAGE_CHOICES,
                        db_index=True,
                        default="az",
                        max_length=10,
                        verbose_name="language",
                    ),
                ),
                ("points", models.PositiveIntegerField(default=1)),
                ("tags", models.JSONField(blank=True, default=list, verbose_name="tags")),
                ("explanation", models.TextField(blank=True, verbose_name="explanation")),
                ("fingerprint", models.CharField(blank=True, db_index=True, max_length=64)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.exams.models.bank_question_media_path,
                        verbose_name="image",
                    ),
                ),
                (
                    "video",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=apps.exams.models.bank_question_media_path,
                        validators=[
                            django.core.validators.FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov"]),
                            apps.exams.models.validate_video_size,
                        ],
                        verbose_name="video",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="is_active")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "bank",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="library_questions",
                        to="exams.questionbank",
                        verbose_name="bank",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bank_library_questions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="created_by",
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
            name="BankQuestionOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "label",
                    models.CharField(
                        blank=True,
                        choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E")],
                        max_length=1,
                        null=True,
                    ),
                ),
                ("text", models.TextField(verbose_name="text")),
                ("is_correct", models.BooleanField(default=False, verbose_name="is_correct")),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="options",
                        to="exams.bankquestion",
                        verbose_name="question",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
            },
        ),
        migrations.AddField(
            model_name="examquestion",
            name="source_bank_question",
            field=models.ForeignKey(
                blank=True,
                help_text="source_bank_question",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="exam_questions",
                to="exams.bankquestion",
                verbose_name="source_bank_question",
            ),
        ),
        migrations.AddIndex(
            model_name="bankquestion",
            index=models.Index(fields=["bank", "is_active"], name="bankq_bank_active_idx"),
        ),
        migrations.AddIndex(
            model_name="bankquestion",
            index=models.Index(fields=["bank", "language"], name="bankq_bank_lang_idx"),
        ),
        migrations.AddIndex(
            model_name="bankquestion",
            index=models.Index(fields=["bank", "difficulty"], name="bankq_bank_diff_idx"),
        ),
    ]
