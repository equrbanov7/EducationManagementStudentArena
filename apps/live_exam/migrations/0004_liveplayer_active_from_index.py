# 2026-10-08 (L3): gec qoşulma — oyunçunun oyunda olduğu ilk sualın indeksi.
# ƏLAVƏ sahədir (default=0 — mövcud oyunçular lobbidən gəlib); geri qaytarıla bilər (RemoveField).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0003_liveplayer_best_streak_liveanswer_text_answer"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveplayer",
            name="active_from_index",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
