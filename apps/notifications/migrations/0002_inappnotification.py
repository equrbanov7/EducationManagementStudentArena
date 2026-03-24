import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InAppNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField(blank=True, default="")),
                ("link", models.CharField(blank=True, default="", max_length=500)),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("assignment", "Assignment"),
                            ("exam", "Exam"),
                            ("grade", "Grade / Feedback"),
                            ("system", "System / Admin"),
                            ("course", "Course"),
                            ("live_exam", "Live Exam / Session"),
                        ],
                        db_index=True,
                        default="system",
                        max_length=20,
                    ),
                ),
                ("is_read", models.BooleanField(default=False, db_index=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="in_app_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["recipient", "deleted_at", "is_read"],
                        name="notificatio_recipient_deleted_read_idx",
                    ),
                    models.Index(
                        fields=["recipient", "deleted_at", "created_at"],
                        name="notificatio_recipient_deleted_crt_idx",
                    ),
                ],
            },
        ),
    ]
