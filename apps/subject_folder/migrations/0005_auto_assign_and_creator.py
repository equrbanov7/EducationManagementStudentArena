"""Sahib 2026-11-10: qovluğun avtomatik qrup təyinatı (``auto_assigned`` + ``auto_batch``) və yaradan (``created_by``).

Yalnız nullable / defoltlu sütun əlavəsi (PostgreSQL 11+ — cədvəl yenidən yazılmır), indeks yoxdur; prod üçün
təhlükəsizdir. Mövcud qovluqların təyinatı miqrasiyada YOX — ``subject_folder_auto_assign`` əmri və
``subject_folder.auto_assign_groups`` beat tapşırığı ilə (dry-run / batch / undo).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subject_folder", "0004_drop_duplicate_sub_b_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="folderassignment",
            name="auto_assigned",
            field=models.BooleanField(
                default=False,
                help_text="Sahib 2026-11-10: müəllimin bu fənn + semestrdə tədris etdiyi qrupa AVTOMATİK təyin olunub.",
            ),
        ),
        migrations.AddField(
            model_name="folderassignment",
            name="auto_batch",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Avtomatik təyinatın partiya id-si (``subject_folder_auto_assign --undo --batch``).",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="subjectfolder",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Qovluğu yaradan (boşdursa — köhnə sətir, sahib müəllim göstərilir).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
