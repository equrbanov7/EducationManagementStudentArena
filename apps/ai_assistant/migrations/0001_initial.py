import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIAssistantLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role_name",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("prompt", models.TextField()),
                (
                    "response_summary",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("success", "Success"),
                            ("blocked", "Blocked"),
                            ("rate_limited", "Rate Limited"),
                            ("error", "Error"),
                        ],
                        default="success",
                        max_length=20,
                    ),
                ),
                (
                    "block_reason",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("prompt_tokens", models.PositiveIntegerField(default=0)),
                ("response_tokens", models.PositiveIntegerField(default=0)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ai_assistant_logs",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_assistant_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="aiassistantlog",
            index=models.Index(
                fields=["user", "-created_at"],
                name="ai_assistant_user_cr_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="aiassistantlog",
            index=models.Index(
                fields=["organization", "-created_at"],
                name="ai_assistant_org_cr_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="aiassistantlog",
            index=models.Index(
                fields=["status", "-created_at"],
                name="ai_assistant_status_cr_idx",
            ),
        ),
    ]
