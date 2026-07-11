from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0043_exam_deleted_at_exam_is_deleted"),
    ]

    operations = [
        migrations.AddField(
            model_name="examanswer",
            name="question_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
