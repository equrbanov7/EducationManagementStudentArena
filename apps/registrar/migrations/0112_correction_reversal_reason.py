"""Preserve new operator explanations without inventing reasons for historical reversals."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registrar", "0111_language_level_cohorts")]

    operations = [
        migrations.AddField(
            model_name="correctionreversal",
            name="reason_note",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
