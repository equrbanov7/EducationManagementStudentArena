"""Push bildirişləri (sahib 2026-10-25): mobil tətbiqin FCM cihaz tokenləri.

Cədvəl istifadəçiyə bağlıdır (``organization_id`` YOXDUR) — tenant RLS siyasəti tələb olunmur; bax model şərhi.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_drop_prefix_redundant_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=512, unique=True)),
                (
                    "platform",
                    models.CharField(
                        choices=[("android", "Android"), ("ios", "iOS"), ("web", "Web")],
                        default="android",
                        max_length=10,
                    ),
                ),
                ("app_version", models.CharField(blank=True, default="", max_length=40)),
                ("language", models.CharField(blank=True, default="", max_length=10)),
                ("muted_types", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("deactivated_reason", models.CharField(blank=True, default="", max_length=40)),
                (
                    "user",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["user", "is_active"], name="push_device_user_active_idx")],
            },
        ),
    ]
