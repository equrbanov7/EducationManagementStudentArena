from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0017_question_bank_library"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionbank",
            name="default_question_type",
            field=models.CharField(
                choices=[("test", "test"), ("written", "written")],
                default="test",
                max_length=20,
            ),
        ),
    ]
