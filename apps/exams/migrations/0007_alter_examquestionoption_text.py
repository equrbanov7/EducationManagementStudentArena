from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0006_exam_fair_distribution_ai_balance_and_question_difficulty_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examquestionoption",
            name="text",
            field=models.TextField(verbose_name="text"),
        ),
    ]
