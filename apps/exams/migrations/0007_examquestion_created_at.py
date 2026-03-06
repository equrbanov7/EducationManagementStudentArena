import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0006_examquestion_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="examquestion",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]

