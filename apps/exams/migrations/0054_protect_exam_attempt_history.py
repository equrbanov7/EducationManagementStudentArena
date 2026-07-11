from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0053_alter_examattempt_question_timing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examattempt",
            name="exam",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="attempts",
                to="exams.exam",
            ),
        ),
    ]
