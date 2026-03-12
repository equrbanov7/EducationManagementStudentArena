from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("live_exam", "0003_alter_livesession_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveplayer",
            name="accessory_key",
            field=models.CharField(default="accessory_none", max_length=32),
        ),
    ]
