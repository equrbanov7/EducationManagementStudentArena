from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0112_correction_reversal_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="legacy_qb_fail",
            field=models.BooleanField(
                default=False, help_text="Köhnə sistemdə davamiyyətdən (q/b) kəsilib — rəsmi bal vərəqinə görə."
            ),
        ),
    ]
