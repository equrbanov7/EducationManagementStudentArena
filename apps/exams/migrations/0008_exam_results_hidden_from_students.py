from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0007_alter_examquestionoption_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="results_hidden_from_students",
            field=models.BooleanField(
                default=False,
                help_text="results_hidden_from_students",
                verbose_name="results_hidden_from_students",
            ),
        ),
    ]
