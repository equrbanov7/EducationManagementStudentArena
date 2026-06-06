import django.db.models.deletion
from django.db import migrations, models

EXAM_LANGUAGE_CHOICES = [
    ("az", "Azərbaycan dili"),
    ("en", "English"),
    ("ru", "Русский"),
    ("tr", "Türkçe"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0014_backfill_manual_lock_flag"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExamLanguageVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "language",
                    models.CharField(
                        choices=EXAM_LANGUAGE_CHOICES,
                        default="az",
                        max_length=10,
                        verbose_name="language",
                    ),
                ),
                ("display_name", models.CharField(blank=True, help_text="display_name", max_length=120, verbose_name="display_name")),
                ("is_active", models.BooleanField(default=True, help_text="is_active", verbose_name="is_active")),
                (
                    "question_count_override",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="question_count_override",
                        null=True,
                        verbose_name="question_count_override",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "exam",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="language_variants",
                        to="exams.exam",
                        verbose_name="exam",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
                "ordering": ["language", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="examlanguagevariant",
            index=models.Index(fields=["exam", "is_active"], name="exam_lang_variant_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="examlanguagevariant",
            constraint=models.UniqueConstraint(fields=("exam", "language"), name="exam_language_variant_unique"),
        ),
        migrations.AddField(
            model_name="examquestion",
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
            model_name="examquestion",
            name="language_variant",
            field=models.ForeignKey(
                blank=True,
                help_text="language_variant",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="questions",
                to="exams.examlanguagevariant",
                verbose_name="language_variant",
            ),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="language",
            field=models.CharField(
                blank=True,
                choices=EXAM_LANGUAGE_CHOICES,
                max_length=10,
                null=True,
                verbose_name="language",
            ),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="language_variant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attempts",
                to="exams.examlanguagevariant",
                verbose_name="language_variant",
            ),
        ),
    ]
