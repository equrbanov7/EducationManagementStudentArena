from django.db import migrations, models


class Migration(migrations.Migration):
    # Depends on the last COMMITTED migration (0042) rather than the in-flight
    # soft-delete 0043, so this audit fix ships independently of that WIP. When
    # 0043 lands it becomes a sibling leaf on 0042; a trivial `makemigrations
    # --merge` reconciles the two (both add unrelated fields on different models).
    dependencies = [
        ("exams", "0042_examattempt_room_examattempt_room_computer"),
    ]

    operations = [
        migrations.AddField(
            model_name="examanswer",
            name="question_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
