import apps.live_exam.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0005_livesession_host_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="livesession",
            name="pin",
            field=models.CharField(
                db_index=True,
                default=apps.live_exam.models.generate_pin,
                max_length=8,
                unique=True,
            ),
        ),
    ]
