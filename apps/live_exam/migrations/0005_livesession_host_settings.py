from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0004_liveplayer_accessory_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="livesession",
            name="host_settings",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
