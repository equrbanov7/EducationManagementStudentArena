# 2026-10-08 (L6): oyun gedərkən çıxarılan oyunçu (removed_at) — ƏLAVƏ, null sahə; default menecer
# çıxarılmamışları qaytarır (sxemə təsiri yoxdur). Geri qaytarıla bilər (RemoveField).

import django.db.models.manager
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0004_liveplayer_active_from_index"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="liveplayer",
            options={"base_manager_name": "all_objects"},
        ),
        migrations.AlterModelManagers(
            name="liveplayer",
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddField(
            model_name="liveplayer",
            name="removed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
