from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0059_question_image_replaces_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionsubmission",
            name="import_token",
            field=models.CharField(blank=True, default="", editable=False, max_length=32),
        ),
    ]
