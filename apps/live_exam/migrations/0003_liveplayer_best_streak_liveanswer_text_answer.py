# Audit 2026-09-28 LX-BE: yazılı cavab (typed answer) mətni + ən uzun seriya.
# Hər iki sahə ƏLAVƏDİR (default ilə) — mövcud sətirlərə toxunmur; geri qaytarıla
# bilər (RemoveField).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0002_liveanswer_liveans_session_question_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveplayer",
            name="best_streak",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="liveanswer",
            name="text_answer",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
    ]
