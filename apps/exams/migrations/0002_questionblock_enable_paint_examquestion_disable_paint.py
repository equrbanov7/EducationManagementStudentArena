from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionblock",
            name="enable_paint",
            field=models.BooleanField(blank=True, default=None, help_text="enable_paint", null=True),
        ),
        migrations.AddField(
            model_name="examquestion",
            name="disable_paint",
            field=models.BooleanField(default=False, help_text="disable_paint"),
        ),
    ]
