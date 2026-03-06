from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0005_alter_exam_options_alter_examanswer_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="examquestion",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True, verbose_name="is_active"),
        ),
    ]

