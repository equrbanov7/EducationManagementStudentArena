from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0019_alter_questionbank_default_question_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="examattempt",
            name="marked_question_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="marked_question_ids",
                verbose_name="marked_question_ids",
            ),
        ),
    ]
