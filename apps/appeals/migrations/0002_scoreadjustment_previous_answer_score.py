from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="scoreadjustment",
            name="previous_answer_score",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
    ]
